import uuid

import pytest

from app.db import SessionLocal, engine
from app.rag.core.errors import EmbeddingModelMismatch, UnknownKnowledgeBase
from app.rag.core.types import Chunk
from app.rag.persistence.store import Store
from app.rag.retrieval.search import Searcher, _rerank_text
from tests.rag.fakes import FailingReranker, HashEmbedder, KeywordReranker, ReverseReranker

emb = HashEmbedder()


@pytest.fixture(autouse=True)
async def _dispose():
    yield
    await engine.dispose()


async def seed(store, texts, name=None):
    kb = await store.create_kb(name or f"kb-{uuid.uuid4().hex[:6]}", "d", "dir:/x", "main", "", emb.model, emb.dim)
    chunks = [Chunk(i, "H", t, f"T > H\n{t}", i * 100, i * 100 + len(t)) for i, t in enumerate(texts)]
    await store.replace_document(kb.id, "a.md", "T", "".join(texts), "s", chunks,
                                 await emb.embed_documents([c.index_text for c in chunks]))
    return kb


def searcher(store, reranker, **kw):
    return Searcher(store, emb, reranker, **kw)


async def test_search_without_reranker_returns_rrf_order():
    store = Store(SessionLocal)
    kb = await seed(store, ["回滚部署的步骤说明", "监控面板的使用方法", "完全无关的内容"])
    r = await searcher(store, None).search("回滚部署", [kb.name], 2)
    assert r.reranked is False and len(r.hits) == 2 and r.hits[0].content.startswith("回滚部署")


async def test_rerank_reorders_and_marks_reranked():
    store = Store(SessionLocal)
    kb = await seed(store, ["回滚部署第一条", "回滚部署第二条", "回滚部署第三条"])
    r = await searcher(store, ReverseReranker()).search("回滚部署", [kb.name], 3)
    assert r.reranked is True and all(h.reranked for h in r.hits)
    assert r.hits[0].score >= r.hits[1].score >= r.hits[2].score


async def test_rerank_failure_falls_back():
    store = Store(SessionLocal)
    kb = await seed(store, ["回滚部署的步骤说明"])
    r = await searcher(store, FailingReranker()).search("回滚部署", [kb.name], 5)
    assert r.reranked is False and len(r.hits) == 1


async def test_min_score_filters_after_rerank_only():
    store = Store(SessionLocal)
    kb = await seed(store, ["回滚部署的步骤说明", "zzzz qqqq"])
    r = await searcher(store, KeywordReranker(), min_score=0.5).search("回滚部署", [kb.name], 5)
    assert r.reranked and all(h.score >= 0.5 for h in r.hits)
    fb = await searcher(store, FailingReranker(), min_score=0.99).search("回滚部署", [kb.name], 5)
    assert fb.reranked is False and fb.hits  # threshold is not applied on fallback


async def test_unknown_kb_and_bad_args():
    store = Store(SessionLocal)
    s = searcher(store, None)
    with pytest.raises(UnknownKnowledgeBase):
        await s.search("x", ["nope"], 5)
    with pytest.raises(ValueError):
        await s.search("  ", ["a"], 5)
    with pytest.raises(ValueError):
        await s.search("x", [], 5)


async def test_cross_kb_search_labels_each_hit():
    store = Store(SessionLocal)
    k1, k2 = await seed(store, ["回滚部署甲库内容"]), await seed(store, ["回滚部署乙库内容"])
    r = await searcher(store, None).search("回滚部署", [k1.name, k2.name], 5)
    assert {h.kb for h in r.hits} == {k1.name, k2.name}


def test_rerank_text_prefix():
    from app.rag.core.types import Hit
    h = Hit("k", "d", "p", "Title", "A > B", 0, 1, 1, "body", 0.1)
    assert _rerank_text(h) == "Title > A > B\nbody"
    assert _rerank_text(Hit("k", "d", "p", "Title", "", 0, 1, 1, "body", 0.1)) == "Title\nbody"

class SlowReranker:
    async def rerank(self, query, docs):
        import asyncio
        await asyncio.sleep(5)
        return [1.0] * len(docs)


class ShortReranker:
    async def rerank(self, query, docs):
        return [1.0] * (len(docs) - 1)


class RecordingReranker:
    def __init__(self):
        self.seen = None

    async def rerank(self, query, docs):
        self.seen = docs
        return [0.5] * len(docs)


async def test_rerank_timeout_falls_back_to_the_fused_order():
    store = Store(SessionLocal)
    kb = await seed(store, ["回滚部署的步骤说明", "监控面板的使用方法"])
    r = await searcher(store, SlowReranker(), timeout_s=0.2).search("回滚部署", [kb.name], 5)
    assert r.reranked is False and r.hits and r.hits[0].content.startswith("回滚部署")


async def test_reranker_returning_the_wrong_number_of_scores_falls_back():
    store = Store(SessionLocal)
    kb = await seed(store, ["回滚部署的步骤说明", "回滚部署第二条"])
    r = await searcher(store, ShortReranker()).search("回滚部署", [kb.name], 5)
    assert r.reranked is False and len(r.hits) == 2


async def test_reranker_is_fed_title_heading_and_content():
    store = Store(SessionLocal)
    kb = await seed(store, ["回滚部署的步骤说明"])
    rec = RecordingReranker()
    await searcher(store, rec).search("回滚部署", [kb.name], 5)
    assert rec.seen == ["T > H\n回滚部署的步骤说明"]


async def test_threshold_that_rejects_everything_returns_no_hits_but_reports_reranked():
    store = Store(SessionLocal)
    kb = await seed(store, ["回滚部署的步骤说明"])
    r = await searcher(store, RecordingReranker(), min_score=0.9).search("回滚部署", [kb.name], 5)
    assert r.reranked is True and r.hits == []  # "nothing relevant", not "reranker failed"


async def test_repeated_kb_name_is_deduplicated():
    store = Store(SessionLocal)
    kb = await seed(store, ["回滚部署的步骤说明"])
    r = await searcher(store, None).search("回滚部署", [kb.name, kb.name], 5)
    assert len(r.hits) == 1


async def test_top_k_below_one_returns_one_hit():
    store = Store(SessionLocal)
    kb = await seed(store, ["回滚部署甲", "回滚部署乙"])
    assert len((await searcher(store, None).search("回滚部署", [kb.name], 0)).hits) == 1


async def test_embedding_model_mismatch_is_rejected_before_searching():
    store = Store(SessionLocal)
    kb = await store.create_kb(f"kb-{uuid.uuid4().hex[:6]}", "d", "dir:/x", "main", "", "other-model", emb.dim)
    with pytest.raises(EmbeddingModelMismatch):
        await searcher(store, None).search("x", [kb.name], 5)


async def test_query_is_stripped_before_embedding():
    store = Store(SessionLocal)
    kb = await seed(store, ["回滚部署的步骤说明"])
    r = await searcher(store, None).search("   回滚部署  \n", [kb.name], 5)
    assert r.hits



class ConstantReranker:
    async def rerank(self, query, docs):
        return [0.5] * len(docs)


async def test_equal_rerank_scores_keep_the_fused_order():
    store = Store(SessionLocal)
    kb = await seed(store, ["回滚部署甲", "回滚部署乙", "回滚部署丙"])
    fused = await searcher(store, None).search("回滚部署", [kb.name], 5)
    reranked = await searcher(store, ConstantReranker()).search("回滚部署", [kb.name], 5)
    assert [h.content for h in reranked.hits] == [h.content for h in fused.hits]
    assert reranked.reranked is True
