import uuid

import pytest

from app.db import SessionLocal, engine
from app.rag.core.errors import (
    DocumentNotFound,
    KnowledgeBaseExists,
    SyncInProgress,
    UnknownKnowledgeBase,
)
from app.rag.core.types import Chunk
from app.rag.persistence.store import Store
from tests.rag.fakes import HashEmbedder

emb = HashEmbedder()


@pytest.fixture(autouse=True)
async def _dispose():
    yield
    await engine.dispose()


async def make_kb(store, name=None):
    return await store.create_kb(name or f"kb-{uuid.uuid4().hex[:6]}", "desc", "dir:/x", "main", "", emb.model, emb.dim)


def mk(idx, text, path="H"):
    return Chunk(idx, path, text, f"T > {path}\n{text}", idx * 10, idx * 10 + len(text))


async def put(store, kb, path, texts, sha="s1"):
    chunks = [mk(i, t) for i, t in enumerate(texts)]
    vecs = await emb.embed_documents([c.index_text for c in chunks])
    await store.replace_document(kb.id, path, path, "".join(texts), sha, chunks, vecs)


async def test_unknown_kb_lists_known():
    store = Store(SessionLocal)
    kb = await make_kb(store)
    with pytest.raises(UnknownKnowledgeBase) as e:
        await store.get_kbs([kb.name, "nope"])
    assert kb.name in str(e.value)


async def test_replace_document_swaps_chunks_and_updates_sha():
    store = Store(SessionLocal)
    kb = await make_kb(store)
    await put(store, kb, "a.md", ["alpha one", "alpha two"], "v1")
    assert await store.doc_shas(kb.id) == {"a.md": "v1"}
    await put(store, kb, "a.md", ["beta only"], "v2")
    assert await store.doc_shas(kb.id) == {"a.md": "v2"}
    hits = await store.hybrid_candidates([kb.id], "alpha", await emb.embed_query("alpha"), 10, 10, 60)
    assert [h.content for h in hits] == ["beta only"]  # old chunks are gone


async def test_hybrid_filters_by_kb_and_fuses_both_routes():
    store = Store(SessionLocal)
    k1, k2 = await make_kb(store), await make_kb(store)
    await put(store, k1, "a.md", ["回滚部署的步骤", "监控面板说明"])
    await put(store, k2, "b.md", ["回滚部署的步骤"])
    hits = await store.hybrid_candidates([k1.id], "回滚部署", await emb.embed_query("回滚部署"), 10, 10, 60)
    assert hits and all(h.kb == k1.name for h in hits)
    assert hits[0].content == "回滚部署的步骤"
    assert hits[0].doc_chars > 0 and hits[0].path == "a.md"


async def test_keyword_route_alone_can_recall():
    store = Store(SessionLocal)
    kb = await make_kb(store)
    await put(store, kb, "a.md", ["错误码 E4021 表示超时", "其他无关内容很多很多"])
    far_vec = [0.0] * 1023 + [1.0]  # semantically unrelated query vector
    hits = await store.hybrid_candidates([kb.id], "E4021", far_vec, 10, 10, 60)
    assert hits[0].content.startswith("错误码 E4021")


async def test_delete_documents_cascades():
    store = Store(SessionLocal)
    kb = await make_kb(store)
    await put(store, kb, "a.md", ["x one"]); await put(store, kb, "b.md", ["y two"])
    await store.delete_documents(kb.id, ["a.md"])
    assert list(await store.doc_shas(kb.id)) == ["b.md"]


async def test_read_range_pages_document():
    store = Store(SessionLocal)
    kb = await make_kb(store)
    await put(store, kb, "a.md", ["0123456789"])
    doc_id = (await store.hybrid_candidates([kb.id], "0123456789", await emb.embed_query("0123456789"), 5, 5, 60))[0].doc_id
    page = await store.read_range(uuid.UUID(doc_id), 2, 4)
    assert (page.text, page.offset, page.total_chars, page.has_more) == ("2345", 2, 10, True)
    last = await store.read_range(uuid.UUID(doc_id), 8, 100)
    assert last.text == "89" and last.has_more is False
    with pytest.raises(DocumentNotFound):
        await store.read_range(uuid.uuid4(), 0, 10)


async def test_sync_lock_is_exclusive_and_released():
    store = Store(SessionLocal)
    kb = await make_kb(store)
    async with store.sync_lock(kb):
        with pytest.raises(SyncInProgress):
            async with store.sync_lock(kb):
                pass
    async with store.sync_lock(kb):
        pass


async def test_sync_lock_is_released_after_an_exception_inside():
    store = Store(SessionLocal)
    kb = await make_kb(store)
    with pytest.raises(RuntimeError):
        async with store.sync_lock(kb):
            raise RuntimeError("sync blew up")
    async with store.sync_lock(kb):  # must be acquirable again
        pass


async def test_sync_lock_is_released_after_a_sql_error_inside():
    from sqlalchemy import text
    store = Store(SessionLocal)
    kb = await make_kb(store)
    with pytest.raises(Exception):
        async with store.sync_lock(kb) as conn:
            await conn.execute(text("SELECT 1/0"))  # aborts the lock's own transaction
    async with store.sync_lock(kb):
        pass


async def test_sync_lock_is_released_when_the_task_is_cancelled():
    import asyncio
    store = Store(SessionLocal)
    kb = await make_kb(store)

    async def hold():
        async with store.sync_lock(kb):
            await asyncio.sleep(30)

    task = asyncio.create_task(hold())
    await asyncio.sleep(0.3)
    with pytest.raises(SyncInProgress):
        async with store.sync_lock(kb):
            pass
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with store.sync_lock(kb):
        pass


async def test_mark_synced_and_failed():
    store = Store(SessionLocal)
    kb = await make_kb(store)
    await store.mark_failed(kb.id, "boom")
    info = [i for i in await store.list_kbs() if i.name == kb.name][0]
    assert info.last_error == "boom" and info.synced_at is None
    await store.mark_synced(kb.id, "rev1")
    info = [i for i in await store.list_kbs() if i.name == kb.name][0]
    assert info.last_error is None and info.synced_at is not None
    assert (await store.get_kb(kb.name)).last_commit == "rev1"


async def test_equal_scores_are_ordered_by_path_then_chunk_index():
    store = Store(SessionLocal)
    kb = await make_kb(store)
    # Identical content and identical vectors: every score is exactly equal, so only the tiebreaker orders them.
    for path in ("c.md", "a.md", "b.md"):
        await put(store, kb, path, ["same text 回滚部署"])
    qv = await emb.embed_query("same text 回滚部署")
    runs = {
        tuple(h.path for h in await store.hybrid_candidates([kb.id], "回滚部署", qv, 10, 10, 60))
        for _ in range(10)
    }
    assert runs == {("a.md", "b.md", "c.md")}


async def test_create_kb_with_a_duplicate_name_raises_a_domain_error():
    store = Store(SessionLocal)
    kb = await make_kb(store)
    with pytest.raises(KnowledgeBaseExists) as exc:
        await make_kb(store, kb.name)
    assert kb.name in str(exc.value)
    assert [i.name for i in await store.list_kbs()].count(kb.name) == 1  # the session is still usable


async def test_replace_document_rejects_mismatched_chunk_and_vector_counts():
    store = Store(SessionLocal)
    kb = await make_kb(store)
    chunks = [mk(0, "one"), mk(1, "two")]
    with pytest.raises(ValueError, match="2 chunks but 1 vectors"):
        await store.replace_document(kb.id, "a.md", "A", "onetwo", "s", chunks, [[0.0] * 1024])
    assert await store.doc_shas(kb.id) == {}  # nothing was written


async def test_read_range_clamps_negative_arguments():
    store = Store(SessionLocal)
    kb = await make_kb(store)
    await put(store, kb, "a.md", ["0123456789"])
    doc_id = (await store.hybrid_candidates([kb.id], "0123456789", await emb.embed_query("0123456789"), 5, 5, 60))[0].doc_id
    page = await store.read_range(uuid.UUID(doc_id), -3, 4)
    assert (page.offset, page.text) == (0, "0123")
    assert (await store.read_range(uuid.UUID(doc_id), 2, -5)).text == ""
