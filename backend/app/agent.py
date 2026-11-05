from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessageChunk
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.config import settings
from app.tools import TOOLS

class ReasoningChatOpenAI(ChatOpenAI):
    """ChatOpenAI that keeps the non-standard `reasoning_content` stream field.

    ChatOpenAI drops provider-specific fields; the chain of thought of reasoning
    models behind OpenAI-compatible proxies arrives in `delta.reasoning_content`.
    """

    def _convert_chunk_to_generation_chunk(self, chunk, default_chunk_class, base_generation_info):
        generation = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if generation is None:
            return None
        choices = chunk.get("choices") or []
        delta = (choices[0].get("delta") or {}) if choices else {}
        reasoning = delta.get("reasoning_content")
        if reasoning and isinstance(generation.message, AIMessageChunk):
            generation.message.additional_kwargs["reasoning_content"] = reasoning
        return generation


SYSTEM_PROMPT = "你是一个乐于助人的中文助手。需要时可以调用工具获取当前时间或进行计算。"


def build_chat_model() -> ReasoningChatOpenAI:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set (see backend/.env.example)")
    return ReasoningChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or None,
        streaming=True,
    )


def build_agent(model: BaseChatModel, checkpointer: BaseCheckpointSaver):
    return create_agent(
        model, TOOLS, system_prompt=SYSTEM_PROMPT, checkpointer=checkpointer
    )
