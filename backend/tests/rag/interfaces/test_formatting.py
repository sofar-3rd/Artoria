from datetime import datetime, timezone

from app.rag.core.errors import UnknownKnowledgeBase
from app.rag.core.types import DocPage, Hit, KbInfo, SearchResult
from app.rag.interfaces.formatting import format_error, format_hits, format_kbs, format_page


def hit(**kw):
    base = dict(kb="platform", doc_id="d1", path="guides/deploy.md", title="部署指南",
                heading_path="部署指南 > 回滚", start=1240, end=2310, doc_chars=18420,
                content="body text", score=0.9, reranked=True)
    return Hit(**{**base, **kw})


def test_format_hits_block():
    out = format_hits(SearchResult([hit()], True), ["platform"])
    assert out.splitlines()[0] == "[1] kb: platform | doc_id: d1 | path: guides/deploy.md"
    assert "title: 部署指南 | section: 部署指南 > 回滚" in out
    assert "chars: 1240-2310 of 18420 | reranked: true" in out
    assert out.rstrip().endswith("body text")


def test_format_hits_empty_message():
    out = format_hits(SearchResult([], True), ["a", "b"])
    assert out.startswith("No relevant content found in: a, b")


def test_format_hits_without_section():
    out = format_hits(SearchResult([hit(heading_path="")], False), ["platform"])
    assert "section:" not in out and "reranked: false" in out


def test_format_page_has_more_footer():
    p = DocPage("d1", "a.md", "A", "abcd", 10, 100, True)
    out = format_page(p)
    assert out.startswith("doc: a.md | title: A | chars 10-14 of 100 | has_more: true")
    assert "offset=14" in out
    assert "offset=" not in format_page(DocPage("d1", "a.md", "A", "abcd", 96, 100, False))


def test_format_kbs():
    ts = datetime(2026, 11, 5, tzinfo=timezone.utc)
    out = format_kbs([KbInfo("platform", "平台文档", 12, ts, None), KbInfo("new", "empty", 0, None, "boom")])
    assert "platform" in out and "平台文档" in out and "12 documents" in out
    assert "never synced" in out


def test_format_error():
    assert format_error(UnknownKnowledgeBase("x", ["a"])).startswith("error: unknown knowledge base 'x'")


def test_format_kbs_shows_a_failed_sync_so_the_model_can_warn_about_stale_content():
    ts = datetime(2026, 11, 5, tzinfo=timezone.utc)
    out = format_kbs([KbInfo("ops", "runbooks", 4, ts, "docs/a.md: no extractable text")])
    assert "last sync failed: docs/a.md: no extractable text" in out


def test_format_kbs_truncates_a_very_long_sync_error():
    out = format_kbs([KbInfo("ops", "runbooks", 4, None, "x" * 5000)])
    assert len(out) < 400


def test_format_kbs_with_no_knowledge_bases():
    assert format_kbs([]) == "No knowledge bases are available."


def test_format_hits_numbers_every_hit_and_separates_them():
    out = format_hits(SearchResult([hit(path="a.md"), hit(path="b.md")], True), ["platform"])
    assert "[1] kb: platform" in out and "[2] kb: platform" in out
    assert out.index("a.md") < out.index("b.md")
