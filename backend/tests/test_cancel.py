import asyncio
import json

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from langchain_core.outputs import ChatGenerationChunk
from langchain_core.tools import tool

from app.chat_stream import drain_wrap_ups
from app.history import CANCELLED_TEXT, find_dangling
from tests.fakes import Scripted
from tests.test_chat import chat, new_thread
from tests.test_telemetry import turns_of

SLOW = {"name": "slow_tool", "args": {}, "id": "s1"}
seen: dict[str, bool] = {}


class Gated(Scripted):
    """Streams the first `hang_after` words, then blocks until cancelled."""

    hang_after: int = 2

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        msg = self._next()
        words = msg.content.split(" ")
        try:
            for i, word in enumerate(words):
                suffix = " " if i < len(words) - 1 else ""
                yield ChatGenerationChunk(message=AIMessageChunk(content=word + suffix))
                if i + 1 == self.hang_after:
                    await asyncio.Event().wait()
        except asyncio.CancelledError:
            seen["model"] = True
            raise


@pytest.fixture(autouse=True)
def _reset_seen():
    seen.clear()


@pytest.fixture
def slow_tool(monkeypatch):
    started = asyncio.Event()

    @tool
    async def slow_tool() -> str:
        """Block until cancelled."""
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            seen["tool"] = True
            raise
        return "never"

    import app.agent

    monkeypatch.setattr(app.agent, "TOOLS", [slow_tool])
    return started


def make_scope(tid: str) -> dict:
    path = f"/api/threads/{tid}/chat"
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"content-type", b"application/json")],
        "server": ("test", 80),
        "client": ("test", 1),
    }


class Call:
    """One raw ASGI call whose disconnect we control."""

    def __init__(self, app, tid: str, message: str = "hi", fail_send_after: int | None = None):
        self.sent: list[dict] = []
        self.disconnect = asyncio.Event()
        self._body_sent = False
        self._fail_after = fail_send_after
        self.task = asyncio.create_task(app(make_scope(tid), self._receive, self._send))
        self._body = json.dumps({"message": message}).encode()

    async def _receive(self):
        if not self._body_sent:
            self._body_sent = True
            return {"type": "http.request", "body": self._body, "more_body": False}
        await self.disconnect.wait()
        return {"type": "http.disconnect"}

    async def _send(self, message):
        if self._fail_after is not None and len(self.sent) >= self._fail_after:
            raise OSError("client gone")
        self.sent.append(message)

    @property
    def text(self) -> str:
        return b"".join(m.get("body", b"") for m in self.sent).decode()

    async def wait_for(self, predicate, timeout: float = 5.0) -> None:
        async with asyncio.timeout(timeout):
            while not predicate():
                await asyncio.sleep(0.01)

    async def finish(self, timeout: float = 5.0) -> None:
        async with asyncio.timeout(timeout):
            await self.task


async def state_messages(app, tid):
    state = await app.state.agent.aget_state({"configurable": {"thread_id": tid}})
    return state.values["messages"]


async def test_disconnect_during_model_stream_cancels_model(running_app):
    script = [AIMessage(content="alpha beta gamma")]
    async with running_app(script, model_cls=Gated) as (app, c):
        tid = await new_thread(c)
        call = Call(app, tid)
        await call.wait_for(lambda: "beta" in call.text)
        call.disconnect.set()
        await call.finish()

        assert seen.get("model") is True
        turns = turns_of(tid)
        assert [t["status"] for t in turns] == ["cancelled"]


async def test_disconnect_during_tool_closes_tool_call(running_app, slow_tool):
    script = [AIMessage(content="calling", tool_calls=[SLOW]), AIMessage(content="after")]
    async with running_app(script) as (app, c):
        tid = await new_thread(c)
        call = Call(app, tid)
        await call.wait_for(slow_tool.is_set)
        call.disconnect.set()
        await call.finish()

        assert seen.get("tool") is True
        messages = await state_messages(app, tid)
        assert find_dangling(messages) == []
        closed = [m for m in messages if isinstance(m, ToolMessage)]
        assert [(m.tool_call_id, m.content) for m in closed] == [("s1", CANCELLED_TEXT)]
        # The finished model step stays in the checkpoint exactly once.
        assert [m.content for m in messages if isinstance(m, AIMessage)] == ["calling"]
        assert [t["status"] for t in turns_of(tid)] == ["cancelled"]


async def test_conversation_continues_after_cancel(running_app):
    script = [AIMessage(content="alpha beta gamma"), AIMessage(content="fine now")]
    async with running_app(script, model_cls=Gated) as (app, c):
        tid = await new_thread(c)
        call = Call(app, tid)
        await call.wait_for(lambda: "beta" in call.text)
        call.disconnect.set()
        await call.finish()

        app.state.test_model.hang_after = 0  # second reply streams to the end
        _, events = await chat(c, tid, "again")
        assert events[-1][0] == "done"
        assert "error" not in [n for n, _ in events]
        view = (await c.get(f"/api/threads/{tid}/messages")).json()
        assert [m["role"] for m in view][-2:] == ["user", "assistant"]
        assert view[-1]["content"] == "fine now"  # first scripted reply was cancelled
        assert [t["status"] for t in turns_of(tid)] == ["cancelled", "ok"]


async def test_send_oserror_is_treated_as_disconnect(running_app):
    script = [AIMessage(content="alpha beta gamma")]
    async with running_app(script, model_cls=Gated) as (app, c):
        tid = await new_thread(c)
        # Allow response.start plus one body chunk, then every send fails.
        call = Call(app, tid, fail_send_after=2)
        await call.finish()

        assert seen.get("model") is True
        assert [t["status"] for t in turns_of(tid)] == ["cancelled"]


async def test_asgi_task_cancel_still_finalizes(running_app):
    script = [AIMessage(content="alpha beta gamma")]
    async with running_app(script, model_cls=Gated) as (app, c):
        tid = await new_thread(c)
        call = Call(app, tid)
        await call.wait_for(lambda: "beta" in call.text)
        call.task.cancel()  # what uvicorn does to in-flight requests on shutdown
        with pytest.raises(asyncio.CancelledError):
            await call.finish()
        await drain_wrap_ups()  # what the lifespan does before closing the pool

        assert seen.get("model") is True
        assert [t["status"] for t in turns_of(tid)] == ["cancelled"]


async def test_wrap_up_failure_does_not_hang_the_request(running_app, monkeypatch):
    script = [AIMessage(content="alpha beta gamma")]
    async with running_app(script, model_cls=Gated) as (app, c):
        tid = await new_thread(c)

        import app.chat_stream as cs

        real = cs.repair_dangling
        calls = 0

        async def flaky(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls > 1:  # the first call is the pre-run repair; fail the wrap-up one
                raise RuntimeError("db down")
            return await real(*args, **kwargs)

        monkeypatch.setattr(cs, "repair_dangling", flaky)

        call = Call(app, tid)
        await call.wait_for(lambda: "beta" in call.text)
        call.disconnect.set()
        await call.finish()

        assert calls == 2
        # Telemetry is still written even though closing tool calls failed.
        assert [t["status"] for t in turns_of(tid)] == ["cancelled"]


async def test_tool_cut_off_by_cancel_is_recorded_as_cancelled(running_app, slow_tool):
    from tests.test_telemetry import tools_of

    script = [AIMessage(content="calling", tool_calls=[SLOW])]
    async with running_app(script) as (app, c):
        tid = await new_thread(c)
        call = Call(app, tid)
        await call.wait_for(slow_tool.is_set)
        await asyncio.sleep(0.2)
        call.disconnect.set()
        await call.finish()

        turn = turns_of(tid)[0]
        (row,) = tools_of(turn["id"])
        assert row["status"] == "cancelled"
        assert row["duration_ms"] is not None and row["duration_ms"] >= 100
        assert row["started_offset_ms"] + row["duration_ms"] <= turn["duration_ms"]
