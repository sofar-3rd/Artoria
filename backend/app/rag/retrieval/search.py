import asyncio
import logging
import math
import numbers
from dataclasses import replace

from app.rag.core.errors import EmbeddingModelMismatch
from app.rag.core.ports import Embedder, Reranker
from app.rag.core.types import Hit, SearchResult
from app.rag.persistence.store import Store

logger = logging.getLogger(__name__)


def _rerank_text(hit: Hit) -> str:
    """The text the cross-encoder scores: the same `title > heading_path` prefix the chunk was embedded with."""
    head = " > ".join(p for p in (hit.title, hit.heading_path) if p)
    return f"{head}\n{hit.content}"


class Searcher:
    """Hybrid retrieval over one or more knowledge bases, with an optional cross-encoder rerank."""

    def __init__(
        self,
        store: Store,
        embedder: Embedder,
        reranker: Reranker | None,
        *,
        recall: int = 40,
        candidates: int = 20,
        rrf_k: int = 60,
        min_score: float | None = None,
        timeout_s: float = 60.0,
    ):
        self._store = store
        self._embedder = embedder
        self._reranker = reranker
        self._recall = recall
        self._candidates = candidates
        self._rrf_k = rrf_k
        self._min_score = min_score
        self._timeout_s = timeout_s

    async def search(self, query: str, kb_names: list[str], top_k: int) -> SearchResult:
        query = query.strip()
        if not query:
            raise ValueError("query is empty")
        if not kb_names:
            raise ValueError("kbs must contain at least one knowledge base")
        top_k = max(top_k, 1)

        # A repeated name is not an error; deduplicate so the model check and logs see each KB once
        # (the SQL filter is `kb_id = ANY(...)`, which is idempotent anyway).
        kbs = await self._store.get_kbs(list(dict.fromkeys(kb_names)))
        for kb in kbs:
            if kb.embed_model != self._embedder.model or kb.embed_dim != self._embedder.dim:
                raise EmbeddingModelMismatch(kb.name, kb.embed_model, self._embedder.model)

        qvec = await self._embedder.embed_query(query)
        cands = await self._store.hybrid_candidates(
            [kb.id for kb in kbs], query, qvec, self._recall, self._candidates, self._rrf_k
        )
        if self._reranker is None or not cands:
            return SearchResult(cands[:top_k], reranked=False)

        scored = await self._rerank(query, cands)
        if scored is None:  # fall back to the fused order; RRF scores are not comparable to rerank scores
            return SearchResult(cands[:top_k], reranked=False)
        if self._min_score is not None:
            scored = [h for h in scored if h.score >= self._min_score]
        return SearchResult(scored[:top_k], reranked=True)

    async def _rerank(self, query: str, cands: list[Hit]) -> list[Hit] | None:
        try:
            scores = await asyncio.wait_for(
                self._reranker.rerank(query, [_rerank_text(h) for h in cands]), self._timeout_s
            )
            _validate_scores(scores, len(cands))
        except Exception as exc:  # includes TimeoutError: ranking must degrade, never fail the search
            logger.warning("rerank unavailable (%s: %s); falling back to the fused order", type(exc).__name__, exc)
            return None
        order = sorted(range(len(cands)), key=lambda i: -scores[i])  # stable: ties keep the fused order
        return [replace(cands[i], score=float(scores[i]), reranked=True) for i in order]


def _validate_scores(scores, expected: int) -> None:
    """A reranker that returns garbage must trigger the fallback, not a crash or a bogus 'nothing relevant'."""
    if len(scores) != expected:
        raise ValueError(f"reranker returned {len(scores)} scores for {expected} candidates")
    for score in scores:
        # numbers.Real, not (int, float): real rerankers return numpy scalars (np.float32 is not a float).
        if isinstance(score, bool) or not isinstance(score, numbers.Real) or not math.isfinite(score):
            raise ValueError(f"reranker returned an unusable score: {score!r}")
