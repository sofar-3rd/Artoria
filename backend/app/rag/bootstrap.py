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


# Bytes each file has on huggingface.co (checked 2026-11). A file is accepted from 99% of that size: an
# interrupted download is far smaller, while a harmless upstream re-export may differ by a few bytes.
REQUIRED_MODEL_FILES = {
    "bge-m3": {"config.json": 687, "pytorch_model.bin": 2_271_145_830, "tokenizer.json": 17_098_108},
    "bge-reranker-v2-m3": {"config.json": 795, "model.safetensors": 2_271_071_852, "tokenizer.json": 17_098_273},
}
MIN_FRACTION = 0.99


def check_model_files(model_dir: str, need_reranker: bool = True) -> None:
    """Fail at start-up, with the fix in the message, instead of at the first query minutes later.

    Existence is not enough: a download interrupted at 50% leaves `pytorch_model.bin` in place and the
    first query would then fail with a torch error inside a chat stream.
    """
    root = Path(model_dir)
    wanted = {n: f for n, f in REQUIRED_MODEL_FILES.items() if need_reranker or n != "bge-reranker-v2-m3"}
    missing, incomplete = [], []
    for name, files in wanted.items():
        for file, expected in files.items():
            path = root / name / file
            if not path.is_file():
                missing.append(f"{name}/{file}")
            elif path.stat().st_size < expected * MIN_FRACTION:
                incomplete.append(f"{name}/{file} ({path.stat().st_size} of {expected} bytes)")
    problems = []
    if missing:
        problems.append(f"model files not found in {root.resolve()}: {', '.join(missing)}")
    if incomplete:
        problems.append(f"incomplete model files (interrupted download?): {', '.join(incomplete)}")
    if problems:
        raise RuntimeError("; ".join(problems) + "; run backend/scripts/download_models.py")


def _real_components(embedder, reranker, count_tokens):
    """Build the models for whatever was not injected. Importing them is cheap; loading is lazy."""
    from app.rag.inference.device import resolve_device
    from app.rag.inference.embedding import BgeM3Embedder
    from app.rag.inference.rerank import BgeReranker
    from app.rag.inference.tokenizer import make_token_counter

    check_model_files(settings.rag_model_dir, need_reranker=reranker is _DEFAULT)
    root = Path(settings.rag_model_dir)
    try:
        device = resolve_device(settings.rag_device)
    except ValueError as exc:  # same fail-fast path as missing files: the operator sees it at start-up
        raise RuntimeError(str(exc)) from exc
    if embedder is None:
        embedder = BgeM3Embedder(str(root / "bge-m3"), device, settings.rag_embed_batch_size)
    if reranker is _DEFAULT:
        reranker = BgeReranker(str(root / "bge-reranker-v2-m3"), device)
    if count_tokens is None:
        count_tokens = make_token_counter(str(root / "bge-m3"))
    return embedder, reranker, count_tokens
