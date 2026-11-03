import json
import uuid

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.history import CANCELLED_TEXT, find_dangling
from tests.fakes import seed_messages

CALC = {"name": "calculator", "args": {"expression": "1+2"}, "id": "c1"}


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        name, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        events.append((name, data))
    return events


async def chat(c, tid, message):
    r = await c.post(f"/api/threads/{tid}/chat", json={"message": message})
    return r, parse_sse(r.text)


async def new_thread(c):
    return (await c.post("/api/threads")).json()["id"]


async def test_plain_reply_streams_tokens_then_done(running_app):
    async with running_app([AIMessage(content="hello there friend")]) as (_, c):
        tid = await new_thread(c)
        r, events = await chat(c, tid, "hi")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        names = [n for n, _ in events]
        assert names[-1] == "done"
        assert set(names[:-1]) == {"token"}
        assert "".join(d["text"] for n, d in events if n == "token") == "hello there friend"


async def test_tool_call_events_in_order(running_app):
    script = [AIMessage(content="let me add", tool_calls=[CALC]), AIMessage(content="it is 3")]
    async with running_app(script) as (_, c):
        tid = await new_thread(c)
        _, events = await chat(c, tid, "1+2?")
        names = [n for n, _ in events]
        assert names.count("tool_call") == 1 and names.count("tool_result") == 1
        i_call, i_res = names.index("tool_call"), names.index("tool_result")
        last_token = max(i for i, n in enumerate(names) if n == "token")
        assert i_call < i_res < last_token
        assert names[-1] == "done"
        call = events[i_call][1]
        assert call == {"id": "c1", "name": "calculator", "args": {"expression": "1+2"}}
        assert events[i_res][1] == {"id": "c1", "name": "calculator", "result": "3"}


async def test_history_after_tool_chat(running_app):
    script = [AIMessage(content="let me add", tool_calls=[CALC]), AIMessage(content="it is 3")]
    async with running_app(script) as (_, c):
        tid = await new_thread(c)
        await chat(c, tid, "1+2?")
        body = (await c.get(f"/api/threads/{tid}/messages")).json()
        assert [m["role"] for m in body] == ["user", "assistant", "assistant"]
        assert body[1]["content"] == "let me add"
        assert body[1]["tool_calls"][0]["result"] == "3"
        assert body[2]["content"] == "it is 3"


async def test_title_comes_from_first_message_only(running_app):
    script = [AIMessage(content="a"), AIMessage(content="b")]
    async with running_app(script) as (_, c):
        tid = await new_thread(c)
        await chat(c, tid, "x" * 50)
        title = (await c.get("/api/threads")).json()[0]["title"]
        assert title == "x" * 30
        await chat(c, tid, "second message")
        assert (await c.get("/api/threads")).json()[0]["title"] == title


async def test_dangling_tool_call_is_repaired(running_app):
    dangling = {"name": "get_current_time", "args": {}, "id": "dangling1"}
    async with running_app([AIMessage(content="ok")]) as (app, c):
        tid = await new_thread(c)
        await seed_messages(app, tid, [
            HumanMessage("q"),
            AIMessage(content="", tool_calls=[dangling]),
        ])
        _, events = await chat(c, tid, "next question")
        assert events[-1][0] == "done"
        assert "error" not in [n for n, _ in events]

        state = await app.state.agent.aget_state({"configurable": {"thread_id": tid}})
        messages = state.values["messages"]
        assert find_dangling(messages) == []
        cancelled = [m for m in messages if isinstance(m, ToolMessage)]
        assert cancelled[0].tool_call_id == "dangling1"
        assert cancelled[0].content == CANCELLED_TEXT


async def test_model_failure_yields_error_event(running_app):
    # Empty script: the model raises IndexError on first call.
    async with running_app([]) as (_, c):
        tid = await new_thread(c)
        _, events = await chat(c, tid, "hi")
        assert events[-1][0] == "error"


async def test_chat_validation_and_404(running_app):
    async with running_app([]) as (_, c):
        tid = await new_thread(c)
        r = await c.post(f"/api/threads/{tid}/chat", json={"message": "   "})
        assert r.status_code == 422
        r = await c.post(f"/api/threads/{tid}/chat", json={"message": "x" * 5000})
        assert r.status_code == 422
        r = await c.post(f"/api/threads/{uuid.uuid4()}/chat", json={"message": "hi"})
        assert r.status_code == 404
