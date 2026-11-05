from typing import Protocol

from app.rag.core.types import LoadedDoc, Snapshot


class Embedder(Protocol):
    model: str
    dim: int

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class Reranker(Protocol):
    async def rerank(self, query: str, docs: list[str]) -> list[float]:
        """Return one relevance score in [0, 1] per doc, aligned with `docs`."""


class DocSource(Protocol):
    async def snapshot(self) -> Snapshot: ...


class Loader(Protocol):
    def load(self, path: str, raw: bytes) -> LoadedDoc: ...
