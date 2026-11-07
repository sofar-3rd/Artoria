import uuid
from datetime import datetime, timedelta, timezone

import psycopg
from langchain_core.messages import AIMessage

from tests.conftest import TEST_URL
from tests.test_chat import CALC, chat, new_thread

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def seed_turns(thread_id: str, rows: list[tuple[str, datetime]]) -> list[uuid.UUID]:
    ids = []
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        for status, started in rows:
            turn_id = uuid.uuid4()
            ids.append(turn_id)
            conn.execute(
                "INSERT INTO turns (id, thread_id, status, started_at, duration_ms,"
                " llm_calls, tool_calls_count) VALUES (%s, %s, %s, %s, 10, 1, 0)",
                (turn_id, uuid.UUID(thread_id), status, started),
            )
    return ids


async def list_all(c, **params) -> list[dict]:
    out, cursor = [], None
    while True:
        q = {**params, "limit": 2}
        if cursor:
            q["cursor"] = cursor
        body = (await c.get("/api/traces", params=q)).json()
        out += body["items"]
        cursor = body["next_cursor"]
        if cursor is None:
            return out


async def test_pagination_covers_every_turn_once_newest_first(running_app):
    async with running_app([]) as (_, c):
        tid = await new_thread(c)
        # Equal timestamps exercise the id tie-break of the cursor.
        times = [BASE, BASE, BASE + timedelta(seconds=1), BASE + timedelta(seconds=1), BASE + timedelta(seconds=2)]
        ids = seed_turns(tid, [("ok", t) for t in times])
        items = await list_all(c)
        assert sorted(i["id"] for i in items) == sorted(str(i) for i in ids)
        assert len({i["id"] for i in items}) == 5
        started = [i["started_at"] for i in items]
        assert started == sorted(started, reverse=True)


async def test_last_page_has_no_cursor(running_app):
    async with running_app([]) as (_, c):
        tid = await new_thread(c)
        seed_turns(tid, [("ok", BASE), ("ok", BASE + timedelta(seconds=1))])
        body = (await c.get("/api/traces", params={"limit": 2})).json()
        assert len(body["items"]) == 2 and body["next_cursor"] is None


async def test_filters_by_status_and_thread(running_app):
    async with running_app([]) as (_, c):
        a, b = await new_thread(c), await new_thread(c)
        seed_turns(a, [("ok", BASE), ("error", BASE + timedelta(seconds=1))])
        seed_turns(b, [("cancelled", BASE + timedelta(seconds=2)), ("error", BASE + timedelta(seconds=3))])
        assert {i["status"] for i in await list_all(c, status="error")} == {"error"}
        assert len(await list_all(c, status="error")) == 2
        only_a = await list_all(c, thread_id=a)
        assert len(only_a) == 2 and {i["thread_id"] for i in only_a} == {a}
        both = await list_all(c, thread_id=b, status="error")
        assert len(both) == 1


async def test_rejects_unknown_status_and_bad_cursor(running_app):
    async with running_app([]) as (_, c):
        assert (await c.get("/api/traces", params={"status": "weird"})).status_code == 422
        assert (await c.get("/api/traces", params={"cursor": "not-a-cursor"})).status_code == 422
        assert (await c.get("/api/traces", params={"limit": 0})).status_code == 422


async def test_list_carries_thread_title(running_app):
    async with running_app([AIMessage(content="hello")]) as (_, c):
        tid = await new_thread(c)
        await chat(c, tid, "my question")
        (item,) = (await c.get("/api/traces")).json()["items"]
        assert item["thread_title"] == "my question"
        assert item["status"] == "ok"


async def test_detail_includes_tools_in_call_order(running_app):
    script = [AIMessage(content="adding", tool_calls=[CALC]), AIMessage(content="it is 3")]
    async with running_app(script) as (_, c):
        tid = await new_thread(c)
        await chat(c, tid, "1+2?")
        (item,) = (await c.get("/api/traces")).json()["items"]
        detail = (await c.get(f"/api/traces/{item['id']}")).json()
        assert detail["id"] == item["id"] and detail["tool_calls_count"] == 1
        (tool,) = detail["tools"]
        assert tool["name"] == "calculator"
        assert tool["args"] == {"expression": "1+2"}
        assert tool["status"] == "ok"
        assert tool["duration_ms"] is not None


async def test_detail_404(running_app):
    async with running_app([]) as (_, c):
        assert (await c.get(f"/api/traces/{uuid.uuid4()}")).status_code == 404
        assert (await c.get("/api/traces/not-a-uuid")).status_code == 422
