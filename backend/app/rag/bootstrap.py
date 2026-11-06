from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.db import SessionLocal
from app.rag.core.ports import DocSource, Embedder, Reranker
from app.rag.ingest.chunking import ChunkConfig
from app.rag.ingest.sources import make_source
from app.rag.ingest.sync import Syncer
from app.rag.persistence.store import KbRef, Store
from app.rag.retrieval.catalog import Catalog
from app.rag.retrieval.search import Searcher


@dataclass
class Rag:
    catalog: Catalog
    searcher: Searcher
    syncer: Syncer
    store: Store
    embedder: Embedder  # the model new knowledge bases are indexed with


def build_rag(
    *,
    embedder: Embedder | None = None,
    reranker: Reranker | None = None,
    count_tokens: Callable[[str], int] | None = None,
    source_factory: Callable[[KbRef], DocSource] | None = None,
) -> Rag:
    """The one place that wires concrete implementations together.

    Every component can be injected (tests pass fakes). Real models are imported inside the function,
    so importing this module never loads torch.
    """
    if embedder is None or count_tokens is None:
        embedder, reranker, count_tokens = _real_components(embedder, reranker, count_tokens)

    store = Store(SessionLocal)
    cache_dir = Path(settings.rag_clone_dir)
    source_factory = source_factory or (
        lambda kb: make_source(kb.repo_url, kb.branch, kb.subdir, cache_dir)
    )
    cfg = ChunkConfig(
        target_tokens=settings.rag_chunk_target_tokens,
        max_tokens=settings.rag_chunk_max_tokens,
        overlap_tokens=settings.rag_chunk_overlap_tokens,
        min_chunk_chars=settings.rag_min_chunk_chars,
    )
    return Rag(
        catalog=Catalog(store),
        searcher=Searcher(
            store,
            embedder,
            reranker,
            recall=settings.rag_recall_candidates,
            candidates=settings.rag_rerank_candidates,
            rrf_k=settings.rag_rrf_k,
            min_score=settings.rag_min_rerank_score,
            timeout_s=settings.rag_rerank_timeout_s,
        ),
        syncer=Syncer(store, embedder, source_factory, cfg, count_tokens, settings.rag_embed_batch_size),
        store=store,
        embedder=embedder,
    )


def _real_components(embedder, reranker, count_tokens):
    """Fill in the components that were not injected. Replaced in the real-model task.

    Until then a real embedder and token counter do not exist, so anything missing is an error that
    names exactly what is missing.
    """
    missing = [name for name, value in (("embedder", embedder), ("count_tokens", count_tokens)) if value is None]
    raise RuntimeError(
        f"missing {' and '.join(missing)}: the real bge models are not wired yet; "
        "inject them into build_rag(), or leave RAG_ENABLED off"
    )
