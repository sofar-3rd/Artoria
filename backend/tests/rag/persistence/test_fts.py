import pytest
from sqlalchemy import text

from app.db import SessionLocal, engine
from app.rag.persistence import fts


@pytest.fixture(autouse=True)
async def _dispose():
    yield
    await engine.dispose()


async def matches(doc: str, query: str):
    terms = fts.search_text(query)
    if not terms:
        return False
    async with SessionLocal() as s:
        await s.execute(text("CREATE TEMP TABLE fts_probe (search_text text)"))
        await s.execute(text("INSERT INTO fts_probe VALUES (:doc)"), {"doc": fts.search_text(doc)})
        await s.execute(text("CREATE INDEX fts_probe_idx ON fts_probe USING bm25(search_text) WITH (text_config='simple')"))
        return (await s.execute(text("""
            SELECT search_text <@> to_bm25query(:query, 'fts_probe_idx') < 0 FROM fts_probe
        """), {"query": terms})).scalar()


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
    assert await matches("的 了 是 anything with spaces", "的 了 是") is False


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
    # User terms are bound data rather than SQL or query operators.
    assert await matches(doc, query) is expected
