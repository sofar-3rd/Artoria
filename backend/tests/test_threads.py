import uuid

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from tests.conftest import count_checkpoints
from tests.fakes import seed_messages


async def test_create_and_list_threads(running_app):
    async with running_app([]) as (_, c):
        r1 = await c.post("/api/threads")
        assert r1.status_code == 201
        assert r1.json()["title"] == "新对话"
        r2 = await c.post("/api/threads")
        listed = (await c.get("/api/threads")).json()
        # newest first
        assert [t["id"] for t in listed] == [r2.json()["id"], r1.json()["id"]]


async def test_delete_thread_clears_checkpoints(running_app):
    async with running_app([]) as (app, c):
        tid = (await c.post("/api/threads")).json()["id"]
        await seed_messages(app, tid, [HumanMessage("hi"), AIMessage("hello")])
        assert count_checkpoints(tid) > 0

        assert (await c.delete(f"/api/threads/{tid}")).status_code == 204
        assert count_checkpoints(tid) == 0
        assert (await c.get("/api/threads")).json() == []
        assert (await c.delete(f"/api/threads/{tid}")).status_code == 404


async def test_messages_endpoint_merges_tool_results(running_app):
    call = {"name": "calculator", "args": {"expression": "1+2"}, "id": "c1"}
    async with running_app([]) as (app, c):
        tid = (await c.post("/api/threads")).json()["id"]
        await seed_messages(app, tid, [
            HumanMessage("q"),
            AIMessage(content="let me", tool_calls=[call]),
            ToolMessage(content="3", tool_call_id="c1", name="calculator"),
            AIMessage(content="it is 3"),
        ])
        body = (await c.get(f"/api/threads/{tid}/messages")).json()
        assert [m["role"] for m in body] == ["user", "assistant", "assistant"]
        assert body[1]["tool_calls"][0]["result"] == "3"
        assert body[2]["content"] == "it is 3"


async def test_messages_of_new_thread_is_empty(running_app):
    async with running_app([]) as (_, c):
        tid = (await c.post("/api/threads")).json()["id"]
        assert (await c.get(f"/api/threads/{tid}/messages")).json() == []


async def test_unknown_thread_returns_404(running_app):
    async with running_app([]) as (_, c):
        tid = uuid.uuid4()
        assert (await c.get(f"/api/threads/{tid}/messages")).status_code == 404
        assert (await c.delete(f"/api/threads/{tid}")).status_code == 404
