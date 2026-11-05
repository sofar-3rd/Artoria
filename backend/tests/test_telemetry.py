import uuid
from typing import Any

import psycopg
from langchain_core.messages import AIMessage
from psycopg.rows import dict_row

from tests.conftest import TEST_URL
from tests.test_chat import CALC, chat, new_thread


def query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    with psycopg.connect(TEST_URL, row_factory=dict_row) as conn:
        return conn.execute(sql, params).fetchall()


def turns_of(thread_id: str) -> list[dict[str, Any]]:
    return query(
        "SELECT * FROM turns WHERE thread_id = %s ORDER BY started_at",
        (uuid.UUID(thread_id),),
    )


def tools_of(turn_id: Any) -> list[dict[str, Any]]:
    return query(
        "SELECT * FROM turn_tool_calls WHERE turn_id = %s ORDER BY seq", (turn_id,)
    )


async def test_plain_turn_records_metrics(running_app):
    async with running_app([AIMessage(content="hello there")]) as (_, c):
        tid = await new_thread(c)
        await chat(c, tid, "hi")

        turns = turns_of(tid)
        assert len(turns) == 1
        turn = turns[0]
        assert turn["status"] == "ok"
        assert turn["llm_calls"] == 1
        assert turn["tool_calls_count"] == 0
        assert turn["ttft_ms"] is not None
        assert turn["first_content_ms"] is not None
        assert turn["duration_ms"] >= turn["first_content_ms"]
        # The Scripted fake reports no usage, so token columns stay NULL.
        assert turn["input_tokens"] is None
        assert turn["output_tokens"] is None
        assert turn["total_tokens"] is None
        assert turn["error"] is None


async def test_tool_call_is_linked_to_turn(running_app):
    script = [AIMessage(content="let me add", tool_calls=[CALC]), AIMessage(content="it is 3")]
    async with running_app(script) as (_, c):
        tid = await new_thread(c)
        await chat(c, tid, "1+2?")

        turns = turns_of(tid)
        assert len(turns) == 1
        turn = turns[0]
        assert turn["llm_calls"] == 2
        assert turn["tool_calls_count"] == 1

        calls = tools_of(turn["id"])
        assert len(calls) == 1
        call = calls[0]
        assert call["name"] == "calculator"
        assert call["args"] == {"expression": "1+2"}
        assert call["tool_call_id"] == "c1"
        assert call["status"] == "ok"
        assert call["seq"] == 0
        assert call["started_offset_ms"] >= 0
        assert call["duration_ms"] is not None
        assert call["result_chars"] == len("3")
        assert call["error"] is None


async def test_multiple_tool_rounds_share_one_turn(running_app):
    script = [
        AIMessage(content="", tool_calls=[
            {"name": "get_current_time", "args": {}, "id": "t1"},
        ]),
        AIMessage(content="", tool_calls=[
            {"name": "calculator", "args": {"expression": "2*3"}, "id": "t2"},
        ]),
        AIMessage(content="done"),
    ]
    async with running_app(script) as (_, c):
        tid = await new_thread(c)
        await chat(c, tid, "time and math")

        turns = turns_of(tid)
        assert len(turns) == 1
        assert turns[0]["llm_calls"] == 3
        assert turns[0]["tool_calls_count"] == 2

        calls = tools_of(turns[0]["id"])
        assert [call["name"] for call in calls] == ["get_current_time", "calculator"]
        assert [call["seq"] for call in calls] == [0, 1]
        assert [call["tool_call_id"] for call in calls] == ["t1", "t2"]
        assert calls[1]["args"] == {"expression": "2*3"}
        assert calls[0]["started_offset_ms"] <= calls[1]["started_offset_ms"]


async def test_model_failure_records_error_turn(running_app):
    # Empty script: the model raises IndexError on first call.
    async with running_app([]) as (_, c):
        tid = await new_thread(c)
        await chat(c, tid, "hi")

        turns = turns_of(tid)
        assert len(turns) == 1
        assert turns[0]["status"] == "error"
        assert turns[0]["error"]
        assert turns[0]["ttft_ms"] is None


async def test_deleting_thread_cascades_telemetry(running_app):
    script = [AIMessage(content="let me add", tool_calls=[CALC]), AIMessage(content="3")]
    async with running_app(script) as (_, c):
        tid = await new_thread(c)
        await chat(c, tid, "1+2?")
        assert turns_of(tid)

        r = await c.delete(f"/api/threads/{tid}")
        assert r.status_code in (200, 204)
        assert turns_of(tid) == []
        assert query("SELECT * FROM turn_tool_calls") == []
