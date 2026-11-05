"""Compare new input and resume after killing a tool's process. See README.md."""

import argparse
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
import uuid
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver

ROOT = Path(__file__).resolve().parent


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def events(directory):
    return [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]


def mock_provider(request):
    messages = json.loads(request.content)["messages"]
    pending = set()
    for message in messages:
        if pending and message["role"] != "tool":
            break
        pending.update(call["id"] for call in message.get("tool_calls", []))
        pending.discard(message.get("tool_call_id"))
    if pending:
        return httpx.Response(400, json={"error": {
            "message": "Missing ToolMessage: " + ", ".join(sorted(pending)),
            "type": "invalid_request_error", "param": "messages", "code": None,
        }})
    message = {"role": "assistant", "content": "Order status: pending."}
    if not any(item["role"] == "tool" for item in messages):
        message = {"role": "assistant", "content": None, "tool_calls": [{
            "id": "call_123", "type": "function", "function": {
                "name": "get_order", "arguments": '{"order_id":"demo-001"}',
            },
        }]}
    return httpx.Response(200, json={
        "id": "chatcmpl-test", "object": "chat.completion", "created": 0, "model": "mock",
        "choices": [{"index": 0, "message": message,
                     "finish_reason": "tool_calls" if "tool_calls" in message else "stop"}],
    })


def worker(args):
    directory = Path(args.output)

    def record(event, **data):
        with (directory / "events.jsonl").open("a") as file:
            file.write(json.dumps({"event": event, "pid": os.getpid(), **data}) + "\n")
            file.flush()
            os.fsync(file.fileno())

    @tool
    def get_order(order_id: str) -> str:
        """Return a synthetic order status. No real business system is modified."""
        record("tool_started", order_id=order_id)
        if args.worker == "crash":
            (directory / "tool.ready").touch()
            while True:
                time.sleep(1)
        record("tool_finished", order_id=order_id)
        return json.dumps({"order_id": order_id, "status": "pending"})

    options = {"model": "simulated-provider", "api_key": "unused", "base_url": "https://mock.invalid/v1"}
    if args.live:
        env = dotenv_values(ROOT.parents[1] / ".env")
        options = {"model": args.model or env.get("OPENAI_MODEL") or "gpt-4.1-mini",
                   "api_key": env["OPENAI_API_KEY"],
                   "base_url": env.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"}
    record("provider", model=options["model"], endpoint_host=urlsplit(options["base_url"]).hostname, live=args.live)
    hooks = {
        "request": [lambda request: record("model_request", body=json.loads(request.content))],
        "response": [lambda response: record("model_response", status_code=response.status_code)],
    }
    with httpx.Client(transport=None if args.live else httpx.MockTransport(mock_provider),
                      event_hooks=hooks, timeout=60, trust_env=False) as client, \
            SqliteSaver.from_conn_string(str(directory / "checkpoint.sqlite")) as saver:
        model = ChatOpenAI(**options, http_client=client, max_retries=0, timeout=60, use_responses_api=False)
        agent = create_agent(model, [get_order], checkpointer=saver)
        config = {"configurable": {"thread_id": "crash-demo"}, "recursion_limit": 6}

        def state():
            snapshot = agent.get_state(config)
            messages = snapshot.values.get("messages", [])
            answered = {message.tool_call_id for message in messages if message.type == "tool"}
            return {"next": list(snapshot.next), "roles": [message.type for message in messages],
                    "checkpoint_id": snapshot.config.get("configurable", {}).get("checkpoint_id"),
                    "pending_calls": [call["id"] for message in messages if message.type == "ai"
                                      for call in message.tool_calls if call["id"] not in answered]}

        result = {"before": state()}
        inputs = {"messages": [HumanMessage(content=(
            "Call get_order with order_id='demo-001' before answering. "
            "After the tool result, answer with its status. Never invent the result."
        ))]} if args.worker == "crash" else None
        if args.worker == "new_human":
            inputs = {"messages": [HumanMessage(content="\u91cd\u8bd5")]}
        try:
            output = agent.invoke(inputs, config=config, durability="sync")
            result.update(status="ok", answer=output["messages"][-1].content)
        except Exception as error:
            result.update(status="error", error_type=type(error).__name__, error=str(error))
        result["after"] = state()
        save(directory / "result.json", result)


def run(args):
    directory = ROOT / "results" / (("live-" if args.live else "mock-") + uuid.uuid4().hex[:8])
    crash = directory / "crash"
    crash.mkdir(parents=True)

    def command(mode, output):
        cmd = [sys.executable, str(Path(__file__).resolve()), "--worker", mode, "--output", str(output)]
        return cmd + (["--live"] if args.live else []) + (["--model", args.model] if args.model else [])

    with (crash / "process.log").open("w") as log:
        process = subprocess.Popen(command("crash", crash), stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 90
            while not (crash / "tool.ready").exists():
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError(f"Tool not reached; inspect {crash}")
                time.sleep(0.05)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
    assert process.returncode == -signal.SIGKILL
    initial = events(crash)
    assert sum(event["event"] == "tool_started" for event in initial) == 1
    assert not any(event["event"] == "tool_finished" for event in initial)
    summary = {"provider_details": initial[0], "crash": {"pid": process.pid, "exit_code": process.returncode},
               "versions": {name: version(name) for name in ["langchain", "langgraph", "langchain-openai",
                                                           "langgraph-checkpoint", "langgraph-checkpoint-sqlite"]},
               "cases": {}}
    checkpoint_ids = []
    for mode in ["new_human", "resume_none"]:
        output = directory / mode
        output.mkdir()
        # Both retry paths start from the same durable state, not from each other's updates.
        with sqlite3.connect(crash / "checkpoint.sqlite") as source, \
                sqlite3.connect(output / "checkpoint.sqlite") as target:
            source.backup(target)
        with (output / "process.log").open("w") as log:
            subprocess.run(command(mode, output), stdout=log, stderr=log, check=True, timeout=90)
        result = json.loads((output / "result.json").read_text())
        before, after = result["before"], result["after"]
        journal = events(output)
        requests = [event["body"]["messages"] for event in journal if event["event"] == "model_request"]
        statuses = [event["status_code"] for event in journal if event["event"] == "model_response"]
        attempts = sum(event["event"] == "tool_started" for event in journal)
        assert before["next"] == ["tools"] and before["roles"] == ["human", "ai"]
        assert len(before["pending_calls"]) == 1
        assert all(event["pid"] != process.pid for event in journal)
        checkpoint_ids.append(before["checkpoint_id"])
        assert requests
        if mode == "new_human":
            assert [message["role"] for message in requests[0]] == ["user", "assistant", "user"]
            if not args.live:
                assert statuses == [400] and attempts == 0
        else:
            assert result["status"] == "ok" and attempts == 1
            assert [message["role"] for message in requests[0]] == ["user", "assistant", "tool"]
            assert requests[0][1]["tool_calls"][0]["id"] == requests[0][2]["tool_call_id"]
            assert after["next"] == [] and after["pending_calls"] == []
        summary["cases"][mode] = {"status": result["status"], "answer": result.get("answer"),
                                  "checkpoint_id": before["checkpoint_id"], "response_statuses": statuses,
                                  "request_roles": [[message["role"] for message in items] for items in requests],
                                  "tool_attempts_after_restart": attempts, "after_roles": after["roles"]}
        print(f"{mode}: HTTP {statuses}, tool attempts {attempts}")
    assert checkpoint_ids[0] == checkpoint_ids[1]
    save(directory / "summary.json", summary)
    print(f"Results: {directory / 'summary.json'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--model")
    parser.add_argument("--worker", choices=["crash", "new_human", "resume_none"])
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.model and not args.live:
        parser.error("--model requires --live")
    worker(args) if args.worker else run(args)
