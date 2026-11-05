import io

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.db import SessionLocal, engine
from app.rag.core.errors import EmbeddingModelMismatch, SourceUnavailable, SyncInProgress
from app.rag.ingest.chunking import ChunkConfig
from app.rag.ingest.sources import DirSource
from app.rag.ingest.sync import Syncer
from app.rag.persistence.store import Store
from tests.rag.fakes import HashEmbedder

CFG = ChunkConfig(target_tokens=200, max_tokens=300, overlap_tokens=0, min_chunk_chars=10)


@pytest.fixture(autouse=True)
async def _dispose():
    yield
    await engine.dispose()


async def setup(tmp_path, emb=None):
    emb = emb or HashEmbedder()
    store = Store(SessionLocal)
    import uuid
    kb = await store.create_kb(f"kb-{uuid.uuid4().hex[:6]}", "d", f"dir:{tmp_path}", "main", "", emb.model, emb.dim)
    syncer = Syncer(store, emb, lambda k: DirSource(tmp_path), CFG, len)
    return store, kb, syncer, emb


def w(root, rel, text):
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text(text, encoding="utf-8")


async def test_first_sync_adds_everything(tmp_path):
    w(tmp_path, "a.md", "# A\n\nalpha body text is here\n"); w(tmp_path, "b.md", "# B\n\nbeta body text is here\n")
    store, kb, syncer, _ = await setup(tmp_path)
    r = await syncer.sync(kb.name)
    assert (r.added, r.changed, r.removed, r.failed) == (2, 0, 0, [])
    assert set(await store.doc_shas(kb.id)) == {"a.md", "b.md"}


async def test_second_sync_with_same_revision_is_noop(tmp_path):
    w(tmp_path, "a.md", "# A\n\nalpha body text is here\n")
    store, kb, syncer, emb = await setup(tmp_path)
    await syncer.sync(kb.name)
    calls = emb.calls
    r = await syncer.sync(kb.name)
    assert (r.added, r.changed, r.removed) == (0, 0, 0) and emb.calls == calls


class CountingStore(Store):
    def __init__(self, sessionmaker):
        super().__init__(sessionmaker)
        self.doc_shas_calls = 0

    async def doc_shas(self, kb_id):
        self.doc_shas_calls += 1
        return await super().doc_shas(kb_id)


async def test_unchanged_revision_returns_before_reading_the_database(tmp_path):
    w(tmp_path, "a.md", "# A\n\nalpha body text is here\n")
    emb = HashEmbedder()
    store = CountingStore(SessionLocal)
    import uuid
    kb = await store.create_kb(f"kb-{uuid.uuid4().hex[:6]}", "d", f"dir:{tmp_path}", "main", "", emb.model, emb.dim)
    syncer = Syncer(store, emb, lambda k: DirSource(tmp_path), CFG, len)
    await syncer.sync(kb.name)
    assert store.doc_shas_calls == 1
    r = await syncer.sync(kb.name)  # same revision: nothing to compare
    assert store.doc_shas_calls == 1
    assert (r.added, r.changed, r.removed, r.unchanged) == (0, 0, 0, 1)


async def test_only_changed_files_are_reembedded(tmp_path):
    w(tmp_path, "a.md", "# A\n\nalpha body text is here\n"); w(tmp_path, "b.md", "# B\n\nbeta body text is here\n")
    store, kb, syncer, emb = await setup(tmp_path)
    await syncer.sync(kb.name)
    before = emb.calls
    w(tmp_path, "a.md", "# A\n\nalpha body text CHANGED\n")
    r = await syncer.sync(kb.name)
    assert (r.added, r.changed, r.removed, r.unchanged) == (0, 1, 0, 1)
    assert 0 < emb.calls - before <= 3


async def test_removed_files_are_deleted(tmp_path):
    w(tmp_path, "a.md", "# A\n\nalpha body text is here\n"); w(tmp_path, "b.md", "# B\n\nbeta body text is here\n")
    store, kb, syncer, _ = await setup(tmp_path)
    await syncer.sync(kb.name)
    (tmp_path / "b.md").unlink()
    r = await syncer.sync(kb.name)
    assert r.removed == 1 and list(await store.doc_shas(kb.id)) == ["a.md"]


async def test_rename_is_remove_plus_add(tmp_path):
    w(tmp_path, "a.md", "# A\n\nalpha body text is here\n")
    store, kb, syncer, _ = await setup(tmp_path)
    await syncer.sync(kb.name)
    (tmp_path / "a.md").rename(tmp_path / "z.md")
    r = await syncer.sync(kb.name)
    assert (r.added, r.removed) == (1, 1)


async def test_failed_file_does_not_block_others_and_blocks_commit(tmp_path):
    w(tmp_path, "good.md", "# G\n\ngood body text is here\n"); w(tmp_path, "bad.md", "   \n")
    store, kb, syncer, _ = await setup(tmp_path)
    r = await syncer.sync(kb.name)
    assert [p for p, _ in r.failed] == ["bad.md"] and r.added == 2
    assert list(await store.doc_shas(kb.id)) == ["good.md"]
    info = [i for i in await store.list_kbs() if i.name == kb.name][0]
    assert info.last_error and "bad.md" in info.last_error and info.synced_at is None
    w(tmp_path, "bad.md", "# Fixed\n\nnow it has content ok\n")
    r2 = await syncer.sync(kb.name)  # revision changed, so it retries
    assert r2.failed == [] and set(await store.doc_shas(kb.id)) == {"good.md", "bad.md"}


async def test_model_mismatch_is_rejected(tmp_path):
    store, kb, _, _ = await setup(tmp_path)
    other = HashEmbedder(); other.model = "other-model"
    syncer = Syncer(store, other, lambda k: DirSource(tmp_path), CFG, len)
    with pytest.raises(EmbeddingModelMismatch):
        await syncer.sync(kb.name)


async def test_empty_source_never_wipes_a_populated_kb(tmp_path):
    w(tmp_path, "a.md", "# A\n\nalpha body text is here\n")
    store, kb, syncer, _ = await setup(tmp_path)
    await syncer.sync(kb.name)
    (tmp_path / "a.md").unlink()
    with pytest.raises(SourceUnavailable):
        await syncer.sync(kb.name)
    assert list(await store.doc_shas(kb.id)) == ["a.md"]
    info = [i for i in await store.list_kbs() if i.name == kb.name][0]
    assert info.last_error and "empty" in info.last_error


async def test_empty_source_on_empty_kb_is_fine(tmp_path):
    store, kb, syncer, _ = await setup(tmp_path)
    r = await syncer.sync(kb.name)
    assert (r.added, r.changed, r.removed, r.failed) == (0, 0, 0, [])


async def test_concurrent_sync_is_rejected(tmp_path):
    w(tmp_path, "a.md", "# A\n\nalpha body text is here\n")
    store, kb, syncer, _ = await setup(tmp_path)
    async with store.sync_lock(kb):
        with pytest.raises(SyncInProgress):
            await syncer.sync(kb.name)

async def test_sync_in_progress_is_not_recorded_as_a_failure(tmp_path):
    w(tmp_path, "a.md", "# A\n\nalpha body text is here\n")
    store, kb, syncer, _ = await setup(tmp_path)
    async with store.sync_lock(kb):
        with pytest.raises(SyncInProgress):
            await syncer.sync(kb.name)
    info = [i for i in await store.list_kbs() if i.name == kb.name][0]
    assert info.last_error is None  # the other run owns the knowledge base; this one just backed off


async def test_non_utf8_markdown_is_a_per_file_failure(tmp_path):
    w(tmp_path, "good.md", "# G\n\ngood body text is here\n")
    (tmp_path / "binary.md").write_bytes(b"# T\n\n\xff\xfe not utf-8")
    store, kb, syncer, _ = await setup(tmp_path)
    r = await syncer.sync(kb.name)
    assert [p for p, _ in r.failed] == ["binary.md"] and "UTF-8" in r.failed[0][1]
    assert list(await store.doc_shas(kb.id)) == ["good.md"]


class ExplodingEmbedder(HashEmbedder):
    async def embed_documents(self, texts):
        if any("poison" in t for t in texts):
            raise RuntimeError("embedding service down")
        return await super().embed_documents(texts)


async def test_embedder_failure_is_a_per_file_failure(tmp_path):
    w(tmp_path, "good.md", "# G\n\ngood body text is here\n")
    w(tmp_path, "bad.md", "# B\n\npoison body text is here\n")
    store, kb, syncer, _ = await setup(tmp_path, ExplodingEmbedder())
    r = await syncer.sync(kb.name)
    assert [p for p, _ in r.failed] == ["bad.md"] and "embedding service down" in r.failed[0][1]
    assert list(await store.doc_shas(kb.id)) == ["good.md"]


async def test_previous_version_survives_a_failed_reindex(tmp_path):
    w(tmp_path, "a.md", "# A\n\noriginal body text is here\n")
    store, kb, syncer, _ = await setup(tmp_path, ExplodingEmbedder())
    await syncer.sync(kb.name)
    old_sha = (await store.doc_shas(kb.id))["a.md"]
    w(tmp_path, "a.md", "# A\n\npoison body text is here\n")
    r = await syncer.sync(kb.name)
    assert [p for p, _ in r.failed] == ["a.md"]
    assert (await store.doc_shas(kb.id))["a.md"] == old_sha  # still the old, searchable version


async def test_removed_files_are_deleted_even_when_another_file_fails(tmp_path):
    w(tmp_path, "keep.md", "# K\n\nkeep body text is here\n"); w(tmp_path, "gone.md", "# G\n\ngone body text is here\n")
    store, kb, syncer, _ = await setup(tmp_path)
    await syncer.sync(kb.name)
    (tmp_path / "gone.md").unlink(); w(tmp_path, "bad.md", "   \n")
    r = await syncer.sync(kb.name)
    assert r.removed == 1 and [p for p, _ in r.failed] == ["bad.md"]
    assert list(await store.doc_shas(kb.id)) == ["keep.md"]


def make_pdf(lines):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for line in lines:
        c.drawString(60, y, line); y -= 20
    c.save()
    return buf.getvalue()


async def test_loading_and_chunking_run_off_the_event_loop_thread(tmp_path):
    import threading
    loop_thread = threading.get_ident()
    seen = set()

    def counting(s: str) -> int:
        seen.add(threading.get_ident())
        return len(s)

    w(tmp_path, "a.md", "# A\n\n" + "alpha body text is here\n\n" * 20)
    emb = HashEmbedder()
    store = Store(SessionLocal)
    import uuid
    kb = await store.create_kb(f"kb-{uuid.uuid4().hex[:6]}", "d", f"dir:{tmp_path}", "main", "", emb.model, emb.dim)
    await Syncer(store, emb, lambda k: DirSource(tmp_path), CFG, counting).sync(kb.name)
    assert seen, "the token counter was never called"
    assert loop_thread not in seen  # CPU-bound work must not block the event loop (SSE streams share it)


async def test_pdf_is_loaded_chunked_and_indexed(tmp_path):
    (tmp_path / "guide.pdf").write_bytes(make_pdf(["Deployment Guide", "Run kubectl rollout undo to roll back."]))
    store, kb, syncer, emb = await setup(tmp_path)
    r = await syncer.sync(kb.name)
    assert (r.added, r.failed) == (1, [])
    hits = await store.hybrid_candidates([kb.id], "kubectl rollout", await emb.embed_query("kubectl rollout"), 10, 10, 60)
    assert hits and hits[0].path == "guide.pdf" and hits[0].title == "guide"

