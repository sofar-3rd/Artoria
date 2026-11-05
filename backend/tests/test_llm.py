from langchain_core.messages import AIMessageChunk

from app.agent import ReasoningChatOpenAI


def make():
    return ReasoningChatOpenAI(model="m", api_key="k", base_url="http://localhost:1/v1")


def convert(model, delta):
    chunk = {"choices": [{"index": 0, "delta": delta, "finish_reason": None}]}
    return model._convert_chunk_to_generation_chunk(chunk, AIMessageChunk, None)


def test_reasoning_content_is_preserved():
    gen = convert(make(), {"role": "assistant", "content": "", "reasoning_content": "hmm"})
    assert gen.message.additional_kwargs["reasoning_content"] == "hmm"


def test_empty_or_missing_reasoning_is_ignored():
    m = make()
    assert "reasoning_content" not in convert(m, {"content": "hi"}).message.additional_kwargs
    assert "reasoning_content" not in convert(
        m, {"content": "hi", "reasoning_content": ""}
    ).message.additional_kwargs
