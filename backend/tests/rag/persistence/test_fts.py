import pytest
from sqlalchemy import text

from app.db import SessionLocal, engine
from app.rag.persistence import fts


@pytest.fixture(autouse=True)
async def _dispose():
    yield
    await engine.dispose()


async def matches(doc: str, query: str):
    sql = f"SELECT {fts.tsvector_sql('doc')} @@ {fts.tsquery_or_sql('q')}"
    async with SessionLocal() as s:
        return (await s.execute(text(sql), {"doc": doc, "q": query})).scalar()


async def query_text(query: str):
    async with SessionLocal() as s:
        return (await s.execute(text(f"SELECT {fts.tsquery_or_sql('q')}::text"), {"q": query})).scalar()


def test_fts_sql_fragments():
    assert fts.tsvector_sql("t") == "to_tsvector('jiebacfg', :t)"
    assert "string_agg(quote_literal(l), ' | ')" in fts.tsquery_or_sql("q")
    assert "btrim(l) <> ''" in fts.tsquery_or_sql("q")


async def test_whitespace_lexeme_never_enters_the_query():
    # pg_jieba emits ' ' for spaces; an OR query containing it matches every chunk that has a space.
    assert "' '" not in (await query_text("回滚 deploy"))
    assert "' '" not in (await query_text("kubectl rollout undo"))


async def test_unrelated_document_does_not_match():
    assert await matches("totally other words here", "回滚 deploy") is False
    assert await matches("totally other words here", "kubectl rollout undo") is False


async def test_related_documents_match_on_any_term():
    assert await matches("如何回滚部署服务", "回滚 deploy") is True
    assert await matches("deploy the service", "回滚 deploy") is True
    assert await matches("run kubectl rollout undo now", "kubectl rollout undo") is True


async def test_error_code_matches_case_insensitively():
    assert await matches("错误码 E4021 表示超时", "e4021") is True
    assert await matches("错误码 E4021 表示超时", "E4021") is True


async def test_stop_word_only_query_matches_nothing_and_does_not_raise():
    assert await query_text("的 了 是") is None
    assert await matches("的 了 是 anything with spaces", "的 了 是") is None  # NULL, i.e. no row


@pytest.mark.parametrize(
    "query,doc,expected",
    [
        ("it's a \"test\" & more | x", "this is a test document", True),
        ("a:b <-> c", "document about b and c", True),
        ("!(x)", "nothing relevant here at all", False),
        ("' ; drop table x; --", "a harmless document", False),
    ],
)
async def test_special_characters_in_user_text_cannot_break_the_query(query, doc, expected):
    # Each lexeme is quote_literal'd, so operators and quotes in user text are plain words.
    assert await matches(doc, query) is expected
