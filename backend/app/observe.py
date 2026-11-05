"""Turn-level telemetry: collect in memory, persist once per request.

`TurnRecorder` is an `AsyncCallbackHandler`, so it sits on the hot path of the
token stream. LangChain awaits async handlers inline, therefore the recorder must
stay IO-free: a single DB round-trip here would stall every token. It only keeps
a handful of counters and dicts and hands them to `persist_turn` at the end of
the request.
"""

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

from app.db import SessionLocal
from app.history import text_of
from app.models import Turn, TurnToolCall

logger = logging.getLogger(__name__)

ARGS_MAX_BYTES = 8 * 1024
ERROR_MAX_CHARS = 500


def _as_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _first(usage: dict, *keys: str) -> int | None:
    for key in keys:
        found = _as_int(usage.get(key))
        if found is not None:
            return found
    return None


def _add(acc: int | None, value: int | None) -> int | None:
    """Accumulate token counts, keeping None when the provider never reports."""
    if value is None:
        return acc
    return (acc or 0) + value


def _usage_of(response: LLMResult) -> tuple[int | None, int | None, int | None]:
    """Read token usage from a result, tolerating providers that report nothing."""
    usage: Any = None
    try:
        usage = getattr(response.generations[0][0].message, "usage_metadata", None)
    except (AttributeError, IndexError, TypeError):
        usage = None
    if not usage:
        llm_output = response.llm_output or {}
        usage = llm_output.get("token_usage") or llm_output.get("usage")
    if not isinstance(usage, dict):
        return None, None, None
    return (
        _first(usage, "input_tokens", "prompt_tokens"),
        _first(usage, "output_tokens", "completion_tokens"),
        _first(usage, "total_tokens"),
    )


def _trim_args(value: Any) -> Any:
    """Normalise tool arguments into JSON-safe data, capped at ARGS_MAX_BYTES."""
    if value is None:
        return None
    try:
        raw = json.dumps(value, ensure_ascii=False, default=repr)
    except (TypeError, ValueError):
        return {"_unserializable": repr(value)[:ERROR_MAX_CHARS]}
    if len(raw.encode("utf-8")) <= ARGS_MAX_BYTES:
        return json.loads(raw)
    return {"_truncated": raw[: ERROR_MAX_CHARS * 4], "_bytes": len(raw)}


def _content_len(value: Any) -> int:
    if isinstance(value, BaseMessage):
        return len(text_of(value.content))
    return len(text_of(value))


class TurnRecorder(AsyncCallbackHandler):
    """Pure in-memory collector for one chat turn. Never performs IO."""

    raise_error = False

    def __init__(self, thread_id: str, model_name: str | None = None) -> None:
        self.thread_id = uuid.UUID(str(thread_id))
        self.turn_id = uuid.uuid4()
        self.started_at = datetime.now(timezone.utc)
        self.model_name = model_name
        self.ttft_ms: int | None = None
        self.first_content_ms: int | None = None
        self.llm_calls = 0
        self.input_tokens: int | None = None
        self.output_tokens: int | None = None
        self.total_tokens: int | None = None
        self.error: str | None = None
        self._t0 = time.perf_counter()
        self._llm_runs: set[str] = set()
        self._tools: dict[str, dict[str, Any]] = {}

    # -- public surface ---------------------------------------------------

    def mark_chunk(self, kind: str = "chunk") -> None:
        """Idempotent TTFT marks. `chunk` = any model output, `content` = answer body."""
        now = self._elapsed_ms()
        if self.ttft_ms is None:
            self.ttft_ms = now
        if kind == "content" and self.first_content_ms is None:
            self.first_content_ms = now

    def mark_error(self, exc: BaseException) -> None:
        self.error = (str(exc) or exc.__class__.__name__)[:ERROR_MAX_CHARS]

    def summary(self, status: str) -> dict[str, Any]:
        tools = [
            {k: v for k, v in row.items() if not k.startswith("_")}
            for row in self._tools.values()
        ]
        return {
            "turn": {
                "id": self.turn_id,
                "thread_id": self.thread_id,
                "status": status,
                "started_at": self.started_at,
                "duration_ms": self._elapsed_ms(),
                "ttft_ms": self.ttft_ms,
                "first_content_ms": self.first_content_ms,
                "llm_calls": self.llm_calls,
                "tool_calls_count": len(tools),
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "total_tokens": self.total_tokens,
                "model": self.model_name,
                "error": self.error,
            },
            "tools": tools,
        }

    # -- model callbacks --------------------------------------------------

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: uuid.UUID,
        parent_run_id: uuid.UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self._count_llm(run_id, metadata)

    async def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: uuid.UUID,
        parent_run_id: uuid.UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self._count_llm(run_id, metadata)

    async def on_llm_new_token(
        self,
        token: Any,
        *,
        chunk: Any = None,
        run_id: uuid.UUID,
        parent_run_id: uuid.UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        # Fallback TTFT path: empty tokens are reasoning-only chunks.
        if token:
            self.mark_chunk("content")

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: uuid.UUID,
        parent_run_id: uuid.UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        input_tokens, output_tokens, total_tokens = _usage_of(response)
        self.input_tokens = _add(self.input_tokens, input_tokens)
        self.output_tokens = _add(self.output_tokens, output_tokens)
        self.total_tokens = _add(self.total_tokens, total_tokens)

    async def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: uuid.UUID,
        parent_run_id: uuid.UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        self.mark_error(error)

    # -- tool callbacks ---------------------------------------------------

    async def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: uuid.UUID,
        parent_run_id: uuid.UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        node = (metadata or {}).get("langgraph_node")
        if node is not None and node != "tools":
            return
        args = inputs if inputs is not None else _loads(input_str)
        self._tools[str(run_id)] = {
            "turn_id": self.turn_id,
            "run_id": str(run_id),
            "tool_call_id": kwargs.get("tool_call_id"),
            "name": serialized.get("name") or _name_from_id(serialized.get("id")),
            "args": _trim_args(args),
            "status": "ok",
            "seq": len(self._tools),
            "started_offset_ms": self._elapsed_ms(),
            "duration_ms": None,
            "result_chars": None,
            "error": None,
            "_t0": time.perf_counter(),
        }

    async def on_tool_end(
        self,
        output: Any,
        *,
        run_id: uuid.UUID,
        parent_run_id: uuid.UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        row = self._tools.get(str(run_id))
        start = row.pop("_t0", None) if row is not None else None
        if row is None or start is None:
            return
        row["duration_ms"] = self._since(start)
        row["result_chars"] = _content_len(output)

    async def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: uuid.UUID,
        parent_run_id: uuid.UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        row = self._tools.get(str(run_id))
        start = row.pop("_t0", None) if row is not None else None
        if row is None or start is None:
            return
        row["status"] = "error"
        row["error"] = (str(error) or error.__class__.__name__)[:ERROR_MAX_CHARS]
        row["duration_ms"] = self._since(start)

    # -- internals --------------------------------------------------------

    def _count_llm(self, run_id: uuid.UUID, metadata: dict[str, Any] | None) -> None:
        key = str(run_id)
        if key in self._llm_runs:
            return
        self._llm_runs.add(key)
        self.llm_calls += 1
        if self.model_name is None and metadata:
            name = metadata.get("ls_model_name")
            if isinstance(name, str):
                self.model_name = name

    def _elapsed_ms(self) -> int:
        return int((time.perf_counter() - self._t0) * 1000)

    @staticmethod
    def _since(start: float) -> int:
        return int((time.perf_counter() - start) * 1000)


def _loads(raw: str) -> Any:
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


def _name_from_id(serialized_id: Any) -> str:
    """`langchain_core.tools:get_current_time` -> `get_current_time`."""
    if not isinstance(serialized_id, str):
        return ""
    return serialized_id.rsplit(":", 1)[-1]


async def persist_turn(recorder: TurnRecorder, status: str) -> None:
    """Write one turn plus its tool rows in a single transaction. Never raises."""
    try:
        data = recorder.summary(status)
        async with SessionLocal() as session:
            session.add(Turn(**data["turn"]))
            await session.flush()
            if data["tools"]:
                session.add_all([TurnToolCall(**row) for row in data["tools"]])
            await session.commit()
    except Exception:
        logger.exception("turn telemetry write failed")
