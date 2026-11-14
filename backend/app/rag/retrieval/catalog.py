import uuid

from app.rag.core.errors import DocumentNotFound
from app.rag.core.types import DocInfo, DocPage, KbInfo
from app.rag.persistence.store import Store

MAX_PAGE_CHARS = 20000


class Catalog:
    """Read-only view of the knowledge bases and their documents."""

    def __init__(self, store: Store):
        self._store = store

    async def list_kbs(self) -> list[KbInfo]:
        return await self._store.list_kbs()

    async def list_documents(self, kb_id: uuid.UUID) -> list[DocInfo]:
        return await self._store.list_documents(kb_id)

    async def read_in_kb(self, kb_id: uuid.UUID, doc_id: str,
                         offset: int = 0, limit: int = 6000) -> DocPage:
        try:
            parsed = uuid.UUID(str(doc_id).strip())
        except ValueError:
            raise DocumentNotFound(str(doc_id)) from None
        # offset/limit are already constrained by the HTTP layer; keep the same bounds here so the
        # catalog is safe for other callers too.
        return await self._store.read_in_kb(
            kb_id, parsed, max(offset, 0), min(max(limit, 1), MAX_PAGE_CHARS)
        )

    async def read_document(self, doc_id: str, offset: int = 0, limit: int = 6000) -> DocPage:
        try:
            parsed = uuid.UUID(str(doc_id).strip())
        except ValueError:
            raise DocumentNotFound(str(doc_id)) from None
        # limit >= 1 so a caller that pages with limit 0 still advances; the store also clamps offset >= 0,
        # this keeps the public contract independent of that.
        return await self._store.read_range(parsed, max(offset, 0), min(max(limit, 1), MAX_PAGE_CHARS))
