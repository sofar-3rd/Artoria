import pytest

from app.rag.persistence import fts


@pytest.mark.parametrize("raw, expected", [
    ("LangGraph 使用 PostgreSQL 保存 checkpoint，实现故障恢复",
     "langgraph 使用 postgresql 保存 checkpoint 实现 故障 恢复"),
    ("alpha beta alpha", "alpha beta alpha"),
    (" \t\r\n", ""),
    ("的 了 是", ""),
    ("错误码 E4021", "错误码 e4021"),
])
def test_search_text_has_consistent_clean_tokens(raw, expected):
    assert fts.search_text(raw) == expected


def test_search_text_preserves_single_letter_words_and_filters_punctuation():
    assert fts.search_text("b c !(x)") == "b c x"
