import pytest

from app.rag.core.errors import UnknownKnowledgeBase
from app.rag.core.types import DocPage, Hit, KbInfo, SearchResult
from app.rag.interfaces.tools import build_kb_tools


class FakeCatalog:
    async def list_kbs(self): return [KbInfo("platform", "平台文档", 3, None, None)]
    async def read_document(self, doc_id, offset=0, limit=6000):
        return DocPage(doc_id, "a.md", "A", "x" * min(limit, 5), offset, 50, True)


class FakeSearcher:
    def __init__(self): self.calls = []
    async def search(self, query, kb_names, top_k):
        self.calls.append((query, kb_names, top_k))
        if not query.strip():
            raise ValueError("query is empty")
        if kb_names == ["nope"]:
            raise UnknownKnowledgeBase("nope", ["platform"])
        h = Hit("platform", "d1", "a.md", "A", "S", 0, 5, 50, "body", 0.5, True)
        return SearchResult([h], True)


def tools():
    s = FakeSearcher()
    return {t.name: t for t in build_kb_tools(FakeCatalog(), s)}, s


def test_tool_names():
    t, _ = tools()
    assert set(t) == {"list_knowledge_bases", "search_knowledge_base", "read_document"}


async def test_list_tool():
    t, _ = tools()
    assert "platform" in await t["list_knowledge_bases"].ainvoke({})


async def test_search_tool_passes_args_and_clamps_top_k():
    t, s = tools()
    out = await t["search_knowledge_base"].ainvoke({"query": "回滚", "kbs": ["platform"], "top_k": 99})
    assert s.calls == [("回滚", ["platform"], 10)] and "doc_id: d1" in out


@pytest.mark.parametrize("asked,expected", [(-4, 1), (0, 1), (1, 1), (10, 10), (11, 10)])
async def test_top_k_is_clamped_to_the_allowed_range(asked, expected):
    t, s = tools()
    await t["search_knowledge_base"].ainvoke({"query": "q", "kbs": ["platform"], "top_k": asked})
    assert s.calls[-1][2] == expected


async def test_search_tool_returns_error_text_not_exception():
    t, _ = tools()
    out = await t["search_knowledge_base"].ainvoke({"query": "x", "kbs": ["nope"]})
    assert out.startswith("error:") and "platform" in out
    assert (await t["search_knowledge_base"].ainvoke({"query": " ", "kbs": ["a"]})).startswith("error:")


async def test_read_document_tool():
    t, _ = tools()
    out = await t["read_document"].ainvoke({"doc_id": "d1", "offset": 5, "limit": 3})
    assert "chars 5-8 of 50" in out and "offset=8" in out


def test_search_tool_schema_requires_kbs():
    t, _ = tools()
    schema = t["search_knowledge_base"].args_schema.model_json_schema()
    assert "kbs" in schema["required"] and "query" in schema["required"]


async def test_invalid_arguments_become_a_readable_error_the_model_can_fix():
    t, s = tools()
    out = await t["search_knowledge_base"].ainvoke({"query": "x", "kbs": []})
    assert out.startswith("error: invalid arguments (kbs:")
    assert "call the tool again" in out and "Traceback" not in out
    assert s.calls == []  # never reached the searcher
    assert (await t["read_document"].ainvoke({"limit": 5})).startswith("error: invalid arguments (doc_id:")


async def test_search_tool_reports_the_reranked_flag_of_the_result_not_of_stale_hits():
    # A hit object may carry reranked=True while the whole search fell back; the result flag is authoritative.
    from app.rag.core.types import Hit, SearchResult

    class FallbackSearcher:
        async def search(self, query, kb_names, top_k):
            return SearchResult([Hit("platform", "d1", "a.md", "A", "S", 0, 5, 50, "body", 0.5, True)], False)

    out = await {x.name: x for x in build_kb_tools(FakeCatalog(), FallbackSearcher())}["search_knowledge_base"].ainvoke(
        {"query": "q", "kbs": ["platform"]}
    )
    assert "reranked: false" in out and "reranked: true" not in out


async def test_unexpected_errors_are_not_swallowed():
    class BrokenSearcher:
        async def search(self, query, kb_names, top_k):
            raise RuntimeError("database exploded")

    broken = {x.name: x for x in build_kb_tools(FakeCatalog(), BrokenSearcher())}["search_knowledge_base"]
    with pytest.raises(RuntimeError, match="database exploded"):
        await broken.ainvoke({"query": "q", "kbs": ["platform"]})


async def test_default_top_k_comes_from_the_builder():
    s = FakeSearcher()
    tool = {x.name: x for x in build_kb_tools(FakeCatalog(), s, default_top_k=3)}["search_knowledge_base"]
    await tool.ainvoke({"query": "q", "kbs": ["platform"]})
    assert s.calls[-1][2] == 3


async def test_search_with_no_hits_says_so_and_names_the_knowledge_bases():
    from app.rag.core.types import SearchResult

    class EmptySearcher:
        async def search(self, query, kb_names, top_k):
            return SearchResult([], True)

    out = await {x.name: x for x in build_kb_tools(FakeCatalog(), EmptySearcher())}["search_knowledge_base"].ainvoke(
        {"query": "q", "kbs": ["platform", "ops"]}
    )
    assert out.startswith("No relevant content found in: platform, ops")


async def test_read_document_errors_are_returned_as_text():
    from app.rag.core.errors import DocumentNotFound

    class MissingCatalog(FakeCatalog):
        async def read_document(self, doc_id, offset=0, limit=6000):
            raise DocumentNotFound(doc_id)

    out = await {x.name: x for x in build_kb_tools(MissingCatalog(), FakeSearcher())}["read_document"].ainvoke({"doc_id": "zzz"})
    assert out == "error: document 'zzz' not found"
