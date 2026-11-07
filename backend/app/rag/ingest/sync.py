import asyncio
import hashlib
import logging
from collections.abc import Callable

from app.rag.core.errors import EmbeddingModelMismatch, SourceUnavailable
from app.rag.core.ports import DocSource, Embedder
from app.rag.core.redact import redact_url
from app.rag.core.types import Snapshot, SyncReport
from app.rag.ingest.chunking import ChunkConfig, chunk_markdown
from app.rag.ingest.loaders import load_with_meta
from app.rag.ingest.plan import plan
from app.rag.persistence.store import KbRef, Store

logger = logging.getLogger(__name__)


class Syncer:
    """Bring one knowledge base in line with its document source, re-embedding only what changed."""

    def __init__(
        self,
        store: Store,
        embedder: Embedder,
        source_factory: Callable[[KbRef], DocSource],
        chunk_cfg: ChunkConfig,
        count_tokens: Callable[[str], int],
        batch_size: int = 16,
    ):
        self._store = store
        self._embedder = embedder
        self._source_factory = source_factory
        self._cfg = chunk_cfg
        self._count_tokens = count_tokens
        self._batch_size = batch_size

    async def sync(self, kb_name: str) -> SyncReport:
        kb = await self._store.get_kb(kb_name)
        if kb.embed_model != self._embedder.model or kb.embed_dim != self._embedder.dim:
            raise EmbeddingModelMismatch(kb.name, kb.embed_model, self._embedder.model)
        # SyncInProgress is raised while entering the lock and must not be recorded as a failure of
        # the knowledge base: another run owns it.
        async with self._store.sync_lock(kb):
            try:
                return await self._run(kb)
            except Exception as exc:
                await self._record_failure(kb, exc)
                raise

    async def _record_failure(self, kb: KbRef, exc: Exception) -> None:
        """Best effort: the caller must see the ORIGINAL error even when the bookkeeping fails too."""
        try:
            await self._store.mark_failed(kb.id, (str(exc) or type(exc).__name__)[:2000])
        except Exception:
            logger.exception("sync %s: could not record the failure %r", kb.name, exc)

    async def _run(self, kb: KbRef) -> SyncReport:
        snap = await self._source_factory(kb).snapshot()
        if snap.revision == kb.last_commit:
            return SyncReport(snap.revision, 0, 0, 0, len(snap.files))

        local = await self._store.doc_shas(kb.id)
        if not snap.files and not snap.skipped and local:
            # An empty snapshot of a populated knowledge base is a broken mount or a wrong path far more
            # often than an intentional wipe; deleting everything is an explicit action, not a sync.
            # A source whose files were all skipped (too large) is not empty: it still lists documents.
            raise SourceUnavailable(
                f"refusing to delete all {len(local)} documents: the source is empty"
            )
        # A document that grew past the size limit disappears from `snap.files`; the planner would call it
        # removed and drop its last good version. Keep that version (stale but searchable) and say so: losing
        # content silently because a file got bigger is worse than serving the older text.
        remote = dict(snap.files)
        kept_stale = {path: local[path] for path in snap.skipped if path in local}
        p = plan({**remote, **kept_stale}, local)

        failed: list[tuple[str, str]] = []
        for path in [*p.added, *p.changed]:
            try:
                await self._index(kb, snap, path)
            except Exception as exc:  # one bad file must not block the others
                logger.warning("sync %s: %s failed: %s", kb.name, path, exc)
                failed.append((path, redact_url(str(exc) or type(exc).__name__)))

        if p.removed:
            await self._store.delete_documents(kb.id, p.removed)

        skipped = sorted(
            (path, reason + (" (the previous version stays searchable)" if path in kept_stale else ""))
            for path, reason in snap.skipped.items()
        )
        if failed:
            summary = redact_url("; ".join(f"{path}: {err}" for path, err in [*failed, *skipped]))[:2000]
            await self._store.mark_failed(kb.id, summary)  # last_commit stays, so the next run retries
        else:
            await self._store.mark_synced(kb.id, snap.revision)
            if skipped:
                # Not a failure and it must not block `synced`: a file over the limit stays over the limit.
                # Recorded in last_error so the operator can see it; the next clean sync clears it.
                await self._store.mark_warning(kb.id, redact_url("; ".join(f"{path}: {r}" for path, r in skipped))[:2000])
        return SyncReport(
            snap.revision, len(p.added), len(p.changed), len(p.removed), len(p.unchanged), failed, skipped
        )

    async def _index(self, kb: KbRef, snap: Snapshot, path: str) -> None:
        # Loading (PDF conversion) and chunking (tokenizer) are CPU-bound: keep them off the event loop.
        doc, chunks = await asyncio.to_thread(self._prepare, snap, path)
        texts = [c.index_text for c in chunks]
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            vectors.extend(await self._embedder.embed_documents(texts[i : i + self._batch_size]))
        await self._store.replace_document(
            kb.id, path, doc.title, doc.markdown, snap.files[path], chunks, vectors
        )

    def _prepare(self, snap: Snapshot, path: str):
        raw = snap.read(path)
        # The sha stored with the document is what later syncs compare against. If the bytes we are about to
        # index are not the bytes that sha was computed from (the file changed between listing and reading,
        # or a shared checkout moved), indexing them would store text under the wrong sha and the next sync
        # would silently never repair it. Fail the file instead; the next run retries it.
        if hashlib.sha256(raw).hexdigest() != snap.files[path]:
            raise SourceUnavailable(f"'{path}' changed while it was being synced; it will be retried on the next sync")
        doc, tags = load_with_meta(path, raw)
        chunked = chunk_markdown(doc.markdown, doc.title, tags, self._cfg, self._count_tokens)
        return doc, chunked.chunks
