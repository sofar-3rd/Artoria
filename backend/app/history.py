from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

CANCELLED_TEXT = "已取消"


def text_of(content) -> str:
    """Flatten message content (str or list of blocks) to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return ""


def to_view(messages: list[BaseMessage]) -> list[dict]:
    """Convert stored messages to the structure the frontend renders.

    Each AIMessage becomes one assistant item; ToolMessages are merged into the
    matching tool call as `result`.
    """
    out: list[dict] = []
    calls: dict[str, dict] = {}
    for m in messages:
        if isinstance(m, HumanMessage):
            out.append({"role": "user", "content": text_of(m.content)})
        elif isinstance(m, AIMessage):
            tool_calls = [
                {"id": tc["id"], "name": tc["name"], "args": tc["args"], "result": None}
                for tc in m.tool_calls
            ]
            content = text_of(m.content)
            if not content and not tool_calls:
                continue
            for tc in tool_calls:
                calls[tc["id"]] = tc
            out.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
        elif isinstance(m, ToolMessage):
            call = calls.get(m.tool_call_id)
            if call is not None:
                call["result"] = text_of(m.content)
    return out


def find_dangling(messages: list[BaseMessage]) -> list[dict]:
    """Return tool calls that have no matching ToolMessage."""
    answered = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
    return [
        tc
        for m in messages
        if isinstance(m, AIMessage)
        for tc in m.tool_calls
        if tc["id"] not in answered
    ]


def cancel_messages(dangling: list[dict]) -> list[ToolMessage]:
    return [
        ToolMessage(
            content=CANCELLED_TEXT,
            tool_call_id=tc["id"],
            name=tc["name"],
            status="error",
        )
        for tc in dangling
    ]
