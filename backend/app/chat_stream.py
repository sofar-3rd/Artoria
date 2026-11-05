import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import aclosing

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from app.history import cancel_messages, find_dangling, text_of
from app.observe import TurnRecorder, persist_turn
from app.sse import sse

logger = logging.getLogger(__name__)

# Wrap-ups still in flight. uvicorn cancels request tasks on shutdown without
# awaiting them, so the app's lifespan waits on these before closing the DB pool.
_wrap_ups: set[asyncio.Task] = set()


async def drain_wrap_ups() -> None:
    if _wrap_ups:
        await asyncio.gather(*_wrap_ups, return_exceptions=True)


async def repair_dangling(agent, config: dict) -> None:
    """Close tool calls left open by an interrupted run so the next turn is valid."""
    state = await agent.aget_state(config)
    pending = find_dangling(state.values.get("messages", []))
    if pending:
        await agent.aupdate_state(
            config, {"messages": cancel_messages(pending)}, as_node="tools"
        )


class ChatRun:
    """One chat request: a single queue fed by the agent and by cancel signals.

    - the pump task runs `agent.astream` and puts events on the queue;
    - anything that wants the run to stop (client disconnect, shutdown) puts a
      `cancel` item on the same queue via `cancel()`;
    - `stream()` is the only consumer: on `cancel` it stops the pump, finalizes
      (dangling tool calls, turn row) and ends.

    LangGraph checkpoints at the end of every step, so everything the agent
    finished is already persisted; only the step that was interrupted is lost.

    A run is local to one ASGI call, so it needs no registry and works with any
    number of worker processes.
    """

    def __init__(self, agent, thread_id: str, text: str, recursion_limit: int) -> None:
        self._agent = agent
        self._text = text
        self._config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": recursion_limit,
        }
        self._recorder = TurnRecorder(thread_id)
        self._queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()
        self._pump_task: asyncio.Task | None = None
        self._finalizing: asyncio.Task | None = None

    def start(self) -> None:
        self._pump_task = asyncio.create_task(self._pump())

    def cancel(self) -> None:
        self._queue.put_nowait(("cancel", None))

    async def _pump(self) -> None:
        put = self._queue.put_nowait
        try:
            await repair_dangling(self._agent, self._config)
            stream = self._agent.astream(
                {"messages": [{"role": "user", "content": self._text}]},
                # Fresh config: `repair_dangling` reuses the plain one, and its
                # aupdate_state must not show up as telemetry.
                {**self._config, "callbacks": [self._recorder]},
                stream_mode=["messages", "updates"],
            )
            async with aclosing(stream):
                async for mode, data in stream:
                    if mode == "messages":
                        chunk, meta = data
                        if (
                            isinstance(chunk, AIMessageChunk)
                            and meta.get("langgraph_node") == "model"
                        ):
                            thought = chunk.additional_kwargs.get("reasoning_content")
                            if thought:
                                self._recorder.mark_chunk("chunk")
                                put(("sse", sse("reasoning", {"text": thought})))
                            piece = text_of(chunk.content)
                            if piece:
                                self._recorder.mark_chunk("content")
                                put(("sse", sse("token", {"text": piece})))
                    elif mode == "updates":
                        for update in data.values():
                            messages = (
                                update.get("messages") if isinstance(update, dict) else None
                            )
                            if not isinstance(messages, list):
                                continue
                            for m in messages:
                                if isinstance(m, AIMessage):
                                    for tc in m.tool_calls:
                                        put(("sse", sse("tool_call", {
                                            "id": tc["id"], "name": tc["name"], "args": tc["args"],
                                        })))
                                elif isinstance(m, ToolMessage):
                                    put(("sse", sse("tool_result", {
                                        "id": m.tool_call_id, "name": m.name,
                                        "result": text_of(m.content),
                                    })))
            put(("end", None))
        except Exception as exc:  # CancelledError is a BaseException and propagates
            put(("error", exc))

    async def stream(self) -> AsyncIterator[str]:
        try:
            while True:
                kind, payload = await self._queue.get()
                if kind == "sse":
                    yield payload
                elif kind == "end":
                    await self._finalize("ok")
                    yield sse("done", {})
                    return
                elif kind == "error":
                    logger.error("chat stream failed", exc_info=payload)
                    self._recorder.mark_error(payload)
                    await self._finalize("error")
                    yield sse("error", {"message": str(payload) or payload.__class__.__name__})
                    return
                else:  # "cancel"
                    await self._finalize("cancelled")
                    return
        except (asyncio.CancelledError, GeneratorExit):
            # The ASGI task itself is going away (server shutdown); still clean up.
            await self._finalize("cancelled")
            raise
        finally:
            if self._pump_task is not None and not self._pump_task.done():
                self._pump_task.cancel()

    async def _finalize(self, status: str) -> None:
        """Run the wrap-up exactly once; shielded so a cancel cannot abort it."""
        if self._finalizing is None:
            self._finalizing = asyncio.ensure_future(self._wrap_up(status))
            _wrap_ups.add(self._finalizing)
            self._finalizing.add_done_callback(_wrap_ups.discard)
        await asyncio.shield(self._finalizing)

    async def _wrap_up(self, status: str) -> None:
        await self._stop_pump()
        if status == "cancelled":
            await self._close_dangling()
        await persist_turn(self._recorder, status)

    async def _stop_pump(self) -> None:
        """Cancel the pump and wait until it unwound (LLM stream and tools closed)."""
        task = self._pump_task
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _close_dangling(self) -> None:
        try:
            await repair_dangling(self._agent, self._config)
        except Exception:
            logger.exception("closing dangling tool calls failed")
