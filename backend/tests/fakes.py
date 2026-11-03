import json

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult


class Scripted(BaseChatModel):
    """Chat model that replays a fixed list of AIMessages, streaming word by word."""

    script: list[AIMessage]
    idx: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _next(self) -> AIMessage:
        msg = self.script[self.idx]
        self.idx += 1
        return msg

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=self._next())])

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        msg = self._next()
        words = msg.content.split(" ") if msg.content else []
        for i, word in enumerate(words):
            suffix = " " if i < len(words) - 1 else ""
            yield ChatGenerationChunk(message=AIMessageChunk(content=word + suffix))
        if msg.tool_calls:
            chunks = [
                {"name": tc["name"], "args": json.dumps(tc["args"]),
                 "id": tc["id"], "index": i}
                for i, tc in enumerate(msg.tool_calls)
            ]
            yield ChatGenerationChunk(
                message=AIMessageChunk(content="", tool_call_chunks=chunks)
            )


async def seed_messages(app, thread_id: str, messages: list) -> None:
    """Write messages straight into the checkpoint without running the model."""
    config = {"configurable": {"thread_id": thread_id}}
    await app.state.agent.aupdate_state(config, {"messages": messages}, as_node="model")
