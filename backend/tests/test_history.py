from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.history import CANCELLED_TEXT, cancel_messages, find_dangling, text_of, to_view

CALL = {"name": "calculator", "args": {"expression": "1+2"}, "id": "c1"}


def test_text_of_handles_blocks():
    assert text_of("abc") == "abc"
    assert text_of([{"type": "text", "text": "a"}, {"type": "image"}, "b"]) == "ab"


def test_to_view_merges_tool_results():
    msgs = [
        HumanMessage("q"),
        AIMessage(content="let me", tool_calls=[CALL]),
        ToolMessage(content="3", tool_call_id="c1", name="calculator"),
        AIMessage(content="it is 3"),
    ]
    assert to_view(msgs) == [
        {"role": "user", "content": "q"},
        {
            "role": "assistant",
            "content": "let me",
            "tool_calls": [
                {"id": "c1", "name": "calculator",
                 "args": {"expression": "1+2"}, "result": "3"}
            ],
        },
        {"role": "assistant", "content": "it is 3", "tool_calls": []},
    ]


def test_to_view_skips_empty_assistant():
    assert to_view([AIMessage(content="")]) == []


def test_to_view_unresolved_call_has_null_result():
    view = to_view([AIMessage(content="", tool_calls=[CALL])])
    assert view[0]["tool_calls"][0]["result"] is None


def test_find_dangling_and_cancel():
    msgs = [HumanMessage("q"), AIMessage(content="", tool_calls=[CALL])]
    dangling = find_dangling(msgs)
    assert [d["id"] for d in dangling] == ["c1"]
    cancelled = cancel_messages(dangling)
    assert cancelled[0].tool_call_id == "c1"
    assert cancelled[0].content == CANCELLED_TEXT
    assert find_dangling(msgs + cancelled) == []
