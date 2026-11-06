import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sqlalchemy.exc import IntegrityError

from app.rag.core.errors import (
    DocumentNotFound,
    KnowledgeBaseExists,
    SyncInProgress,
    UnknownKnowledgeBase,
)
from app.rag.core.types import Chunk, DocPage, Hit, KbInfo
from app.rag.persistence import fts
from app.rag.persistence.models import ChunkRow, Document, KnowledgeBase


@dataclass(frozen=True)
class KbRef:
    id: uuid.UUID
    name: str
    description: str
    repo_url: str
    branch: str
    subdir: str
    embed_model: str
    embed_dim: int
    last_commit: str | None


@dataclass(frozen=True)
class DocRef:
    id: uuid.UUID
    kb_id: uuid.UUID
    path: str
    title: str
    content: str


def _ref(k: KnowledgeBase) -> KbRef:
    return KbRef(k.id, k.name, k.description, k.repo_url, k.branch, k.subdir,
                 k.embed_model, k.embed_dim, k.last_commit)


HYBRID_SQL = f"""
WITH dense AS (
  SELECT c.id, row_number() OVER (ORDER BY c.embedding <=> CAST(:qvec AS vector), d.path, c.idx) AS r
  FROM chunks c JOIN documents d ON d.id = c.doc_id WHERE c.kb_id = ANY(:kb_ids)
  ORDER BY c.embedding <=> CAST(:qvec AS vector), d.path, c.idx LIMIT :recall
), q AS (SELECT {fts.tsquery_or_sql('query')} AS tq),
sparse AS (
  SELECT c.id, row_number() OVER (ORDER BY ts_rank_cd(c.tsv, q.tq) DESC, d.path, c.idx) AS r
  FROM chunks c JOIN documents d ON d.id = c.doc_id, q
  WHERE c.kb_id = ANY(:kb_ids) AND c.tsv @@ q.tq
  ORDER BY ts_rank_cd(c.tsv, q.tq) DESC, d.path, c.idx LIMIT :recall
), fused AS (
  SELECT coalesce(d.id, s.id) AS id,
         coalesce(1.0 / (:rrf_k + d.r), 0) + coalesce(1.0 / (:rrf_k + s.r), 0) AS score
  FROM dense d FULL JOIN sparse s ON d.id = s.id
)
SELECT c.id, k.name AS kb, d.id AS doc_id, d.path, d.title, c.heading_path,
       c.start_char, c.end_char, length(d.content) AS doc_chars, c.content, f.score
FROM fused f JOIN chunks c ON c.id = f.id
JOIN documents d ON d.id = c.doc_id JOIN knowledge_bases k ON k.id = c.kb_id
ORDER BY f.score DESC, d.path, c.idx LIMIT :limit
"""

UPSERT_DOC_SQL = """
INSERT INTO documents (id, kb_id, path, title, content, content_sha)
VALUES (:id, :kb_id, :path, :title, :content, :sha)
ON CONFLICT (kb_id, path) DO UPDATE
SET title = EXCLUDED.title, content = EXCLUDED.content,
    content_sha = EXCLUDED.content_sha, updated_at = now()
RETURNING id
"""

TSV_UPDATE_SQL = (
    f"UPDATE chunks SET tsv = {fts.tsvector_sql('t')} WHERE doc_id = :doc AND idx = :idx"
)

PAGE_SQL = """
SELECT id, path, title,
       substring(content from :offset + 1 for :lim) AS text,
       length(content) AS total
FROM documents WHERE id = :doc_id
"""


def _vector_param(vec: list[float]) -> str:
    return "[" + ",".join(map(str, vec)) + "]"


def _lock_key(kb_id: uuid.UUID) -> int:
    return int.from_bytes(kb_id.bytes[:8], "big", signed=True)


class Store:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]):
        self._sm = sessionmaker

    # --- knowledge bases -------------------------------------------------

    async def create_kb(self, name: str, description: str, repo_url: str, branch: str,
                        subdir: str, embed_model: str, embed_dim: int) -> KbRef:
        async with self._sm() as s:
            kb = KnowledgeBase(name=name, description=description, repo_url=repo_url,
                               branch=branch, subdir=subdir, embed_model=embed_model,
                               embed_dim=embed_dim)
            s.add(kb)
            try:
                await s.flush()
            except IntegrityError as exc:
                await s.rollback()
                if "knowledge_bases_name_key" in str(exc.orig):
                    raise KnowledgeBaseExists(name) from exc
                raise
            ref = _ref(kb)
            await s.commit()
            return ref

    async def get_kbs(self, names: list[str]) -> list[KbRef]:
        async with self._sm() as s:
            found = {
                k.name: _ref(k)
                for k in (await s.execute(
                    select(KnowledgeBase).where(KnowledgeBase.name.in_(names))
                )).scalars()
            }
            for name in names:
                if name not in found:
                    all_names = sorted((await s.execute(
                        select(KnowledgeBase.name)
                    )).scalars().all())
                    raise UnknownKnowledgeBase(name, all_names)
            return [found[n] for n in names]

    async def get_kb(self, name: str) -> KbRef:
        return (await self.get_kbs([name]))[0]

    async def list_kbs(self) -> list[KbInfo]:
        sql = (
            select(KnowledgeBase.name, KnowledgeBase.description,
                   func.count(Document.id).label("doc_count"),
                   KnowledgeBase.synced_at, KnowledgeBase.last_error)
            .select_from(KnowledgeBase)
            .outerjoin(Document, Document.kb_id == KnowledgeBase.id)
            .group_by(KnowledgeBase.id)
            .order_by(KnowledgeBase.name)
        )
        async with self._sm() as s:
            return [KbInfo(r.name, r.description, r.doc_count, r.synced_at, r.last_error)
                    for r in await s.execute(sql)]

    # --- documents -------------------------------------------------------

    async def doc_shas(self, kb_id: uuid.UUID) -> dict[str, str]:
        sql = select(Document.path, Document.content_sha).where(Document.kb_id == kb_id)
        async with self._sm() as s:
            return dict((await s.execute(sql)).all())

    async def replace_document(self, kb_id: uuid.UUID, path: str, title: str, content: str,
                               sha: str, chunks: list[Chunk],
                               vectors: list[list[float]]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError(f"{len(chunks)} chunks but {len(vectors)} vectors for '{path}'")
        async with self._sm() as s:
            async with s.begin():
                doc_id = (await s.execute(text(UPSERT_DOC_SQL), {
                    "id": uuid.uuid4(), "kb_id": kb_id, "path": path, "title": title,
                    "content": content, "sha": sha,
                })).scalar_one()
                await s.execute(delete(ChunkRow).where(ChunkRow.doc_id == doc_id))
                s.add_all([
                    ChunkRow(doc_id=doc_id, kb_id=kb_id, idx=c.idx,
                             heading_path=c.heading_path, start_char=c.start,
                             end_char=c.end, content=c.content, embedding=v)
                    for c, v in zip(chunks, vectors)
                ])
                await s.flush()
                if chunks:
                    await s.execute(text(TSV_UPDATE_SQL), [
                        {"t": c.index_text, "doc": doc_id, "idx": c.idx} for c in chunks
                    ])

    async def delete_documents(self, kb_id: uuid.UUID, paths: list[str]) -> None:
        async with self._sm() as s:
            await s.execute(delete(Document).where(Document.kb_id == kb_id,
                                                   Document.path.in_(paths)))
            await s.commit()

    async def mark_synced(self, kb_id: uuid.UUID, revision: str) -> None:
        await self._update_kb(kb_id, last_commit=revision, synced_at=func.now(),
                              last_error=None)

    async def mark_failed(self, kb_id: uuid.UUID, error: str) -> None:
        await self._update_kb(kb_id, last_error=error)

    async def mark_warning(self, kb_id: uuid.UUID, message: str) -> None:
        """Record something the operator should see after a sync that did succeed (files skipped on purpose)."""
        await self._update_kb(kb_id, last_error=message)

    async def _update_kb(self, kb_id: uuid.UUID, **values) -> None:
        async with self._sm() as s:
            await s.execute(
                update(KnowledgeBase).where(KnowledgeBase.id == kb_id).values(**values)
            )
            await s.commit()

    async def get_document(self, doc_id: uuid.UUID) -> DocRef:
        async with self._sm() as s:
            row = (await s.execute(
                select(Document).where(Document.id == doc_id)
            )).scalar_one_or_none()
            if row is None:
                raise DocumentNotFound(str(doc_id))
            return DocRef(row.id, row.kb_id, row.path, row.title, row.content)

    async def read_range(self, doc_id: uuid.UUID, offset: int, limit: int) -> DocPage:
        offset, limit = max(offset, 0), max(limit, 0)
        async with self._sm() as s:
            row = (await s.execute(text(PAGE_SQL), {
                "doc_id": doc_id, "offset": offset, "lim": limit,
            })).first()
        if row is None:
            raise DocumentNotFound(str(doc_id))
        text_ = row.text or ""
        return DocPage(doc_id=str(row.id), path=row.path, title=row.title, text=text_,
                       offset=offset, total_chars=row.total,
                       has_more=offset + len(text_) < row.total)

    # --- search ----------------------------------------------------------

    async def hybrid_candidates(self, kb_ids: list[uuid.UUID], query: str,
                                qvec: list[float], recall: int, limit: int,
                                rrf_k: int) -> list[Hit]:
        async with self._sm() as s:
            rows = await s.execute(text(HYBRID_SQL), {
                "qvec": _vector_param(qvec), "kb_ids": kb_ids, "query": query,
                "recall": recall, "rrf_k": rrf_k, "limit": limit,
            })
            return [
                Hit(kb=r.kb, doc_id=str(r.doc_id), path=r.path, title=r.title,
                    heading_path=r.heading_path, start=r.start_char, end=r.end_char,
                    doc_chars=r.doc_chars, content=r.content, score=float(r.score),
                    reranked=False)
                for r in rows
            ]

    # --- sync serialisation ----------------------------------------------

    @asynccontextmanager
    async def sync_lock(self, kb: KbRef):
        """Exclusive per-KB lock for a sync run, held by a TRANSACTION-level advisory lock.

        A transaction-level lock is released by COMMIT, ROLLBACK or disconnect, so it survives
        Python exceptions, SQL errors and task cancellation. The session-level variant tied to a
        pooled connection leaks the lock after a SQL error. The per-document write transactions
        run on other connections and do not interact with this one.
        """
        engine = self._sm.kw["bind"]
        async with engine.connect() as conn:
            async with conn.begin():
                got = (await conn.execute(
                    text("SELECT pg_try_advisory_xact_lock(:key)"),
                    {"key": _lock_key(kb.id)},
                )).scalar()
                if not got:
                    raise SyncInProgress(kb.name)
                yield conn
