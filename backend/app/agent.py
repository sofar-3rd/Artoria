from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.config import settings
from app.tools import TOOLS

SYSTEM_PROMPT = "你是一个乐于助人的中文助手。需要时可以调用工具获取当前时间或进行计算。"


def build_chat_model() -> ChatOpenAI:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set (see backend/.env.example)")
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or None,
        streaming=True,
    )


def build_agent(model: BaseChatModel, checkpointer: BaseCheckpointSaver):
    return create_agent(
        model, TOOLS, system_prompt=SYSTEM_PROMPT, checkpointer=checkpointer
    )
