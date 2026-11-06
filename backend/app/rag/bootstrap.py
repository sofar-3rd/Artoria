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


class _Default:
    """Marks an argument that was not supplied (None already has a meaning for the reranker)."""

    def __repr__(self) -> str:
        return "<default>"


_DEFAULT = _Default()


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
    reranker: Reranker | None | _Default = _DEFAULT,
    count_tokens: Callable[[str], int] | None = None,
    source_factory: Callable[[KbRef], DocSource] | None = None,
) -> Rag:
    """The one place that wires concrete implementations together.

    Every component can be injected (tests pass fakes). Real models are imported inside the function,
    so importing this module never loads torch. `reranker=None` means "no reranking" and is respected;
    leaving it out means "use the configured reranker".
    """
    if embedder is None or count_tokens is None or reranker is _DEFAULT:
        embedder, reranker, count_tokens = _real_components(embedder, reranker, count_tokens)

    store = Store(SessionLocal)
    cache_dir = Path(settings.rag_clone_dir)
    source_factory = source_factory or (
        lambda kb: make_source(kb.repo_url, kb.branch, kb.subdir, cache_dir, owner=str(kb.id))
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


REQUIRED_MODEL_FILES = {
    "bge-m3": ("config.json", "pytorch_model.bin", "tokenizer.json"),
    "bge-reranker-v2-m3": ("config.json", "model.safetensors", "tokenizer.json"),
}


def check_model_files(model_dir: str, need_reranker: bool = True) -> None:
    """Fail at start-up, with the fix in the message, instead of at the first query minutes later."""
    root = Path(model_dir)
    wanted = {n: f for n, f in REQUIRED_MODEL_FILES.items() if need_reranker or n != "bge-reranker-v2-m3"}
    missing = [
        f"{name}/{file}"
        for name, files in wanted.items()
        for file in files
        if not (root / name / file).is_file()
    ]
    if missing:
        raise RuntimeError(
            f"model files not found in {root.resolve()}: {', '.join(missing)}; "
            "run backend/scripts/download_models.py"
        )


def _real_components(embedder, reranker, count_tokens):
    """Build the models for whatever was not injected. Importing them is cheap; loading is lazy."""
    from app.rag.inference.device import resolve_device
    from app.rag.inference.embedding import BgeM3Embedder
    from app.rag.inference.rerank import BgeReranker
    from app.rag.inference.tokenizer import make_token_counter

    check_model_files(settings.rag_model_dir, need_reranker=reranker is _DEFAULT)
    root = Path(settings.rag_model_dir)
    device = resolve_device(settings.rag_device)
    if embedder is None:
        embedder = BgeM3Embedder(str(root / "bge-m3"), device, settings.rag_embed_batch_size)
    if reranker is _DEFAULT:
        reranker = BgeReranker(str(root / "bge-reranker-v2-m3"), device)
    if count_tokens is None:
        count_tokens = make_token_counter(str(root / "bge-m3"))
    return embedder, reranker, count_tokens
