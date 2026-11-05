import logging
from collections.abc import AsyncIterator

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from app.history import cancel_messages, find_dangling, text_of
from app.sse import sse

logger = logging.getLogger(__name__)


async def repair_dangling(agent, config: dict) -> None:
    """Close tool calls left open by an interrupted run so the next turn is valid."""
    state = await agent.aget_state(config)
    pending = find_dangling(state.values.get("messages", []))
    if pending:
        await agent.aupdate_state(
            config, {"messages": cancel_messages(pending)}, as_node="tools"
        )


async def run_chat(
    agent, thread_id: str, text: str, recursion_limit: int
) -> AsyncIterator[str]:
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": recursion_limit,
    }
    try:
        await repair_dangling(agent, config)
        stream = agent.astream(
            {"messages": [{"role": "user", "content": text}]},
            config,
            stream_mode=["messages", "updates"],
        )
        async for mode, data in stream:
            if mode == "messages":
                chunk, meta = data
                if (
                    isinstance(chunk, AIMessageChunk)
                    and meta.get("langgraph_node") == "model"
                ):
                    thought = chunk.additional_kwargs.get("reasoning_content")
                    if thought:
                        yield sse("reasoning", {"text": thought})
                    piece = text_of(chunk.content)
                    if piece:
                        yield sse("token", {"text": piece})
            elif mode == "updates":
                for update in data.values():
                    messages = update.get("messages") if isinstance(update, dict) else None
                    if not isinstance(messages, list):
                        continue
                    for m in messages:
                        if isinstance(m, AIMessage):
                            for tc in m.tool_calls:
                                yield sse("tool_call", {
                                    "id": tc["id"], "name": tc["name"], "args": tc["args"],
                                })
                        elif isinstance(m, ToolMessage):
                            yield sse("tool_result", {
                                "id": m.tool_call_id, "name": m.name,
                                "result": text_of(m.content),
                            })
        yield sse("done", {})
    except Exception as exc:  # CancelledError is a BaseException and propagates
        logger.exception("chat stream failed")
        yield sse("error", {"message": str(exc) or exc.__class__.__name__})
