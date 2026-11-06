"""Measure retrieval quality on one knowledge base: dense only, hybrid, and hybrid + rerank.

    cd backend && uv run python -m scripts.eval_retrieval --kb NAME --questions eval/questions.yaml

The question file is YAML: a list of `{q: <question>, expect: <path>, must: <phrase>}`. `expect: none` marks a
question the corpus cannot answer (it measures the false-answer rate instead of the hit rate); `must` is an
optional phrase the answering passage has to contain, because a corpus can hold several files with the same
name (this one has six `SKILL.md`), and "right file" is not the same as "right passage".

All three configurations call the same code the agent uses (`Store.hybrid_candidates` and `Searcher`), only with
the keyword route emptied or the reranker left out, so the numbers describe the shipped pipeline.
"""

import argparse
import asyncio
import statistics
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.config import settings
from app.rag.bootstrap import build_rag
from app.rag.retrieval.search import Searcher


@dataclass(frozen=True)
class Span:
    """One retrieved passage and the question it may answer."""

    question: dict
    path: str
    content: str


def is_answer(question: dict, span: Span) -> bool:
    """Does this passage answer the question: right document, and the expected phrase when one is given?"""
    if question["expect"] == "none" or span.path != question["expect"]:
        return False
    phrase = question.get("must")
    return not phrase or phrase.lower() in span.content.lower()


def hits_within(question: dict, spans: list[Span], k: int) -> bool:
    """Was an answering PASSAGE among the first k? Passages are judged one by one: a document can contribute
    several, and the answering one is not always its highest ranked chunk."""
    return any(is_answer(question, span) for span in spans[:k])


def reciprocal_rank(question: dict, spans: list[Span]) -> float:
    for rank, span in enumerate(spans, start=1):
        if is_answer(question, span):
            return 1.0 / rank
    return 0.0


def load_questions(path: Path) -> list[dict]:
    questions = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(questions, list) or not questions:
        raise SystemExit(f"{path} must be a non-empty YAML list of {{q, expect, must?}}")
    for item in questions:
        if not isinstance(item, dict) or "q" not in item or "expect" not in item:
            raise SystemExit(f"bad question entry: {item!r}")
    return questions


@dataclass
class Outcome:
    spans: list[Span] = field(default_factory=list)
    top_score: float = 0.0


async def run_configuration(rag, kb_name: str, question: dict, *, dense_only: bool, rerank: bool, top_k: int) -> Outcome:
    if dense_only:
        (kb,) = await rag.store.get_kbs([kb_name])
        qvec = await rag.embedder.embed_query(question["q"])
        found = await rag.store.hybrid_candidates(
            [kb.id], "", qvec,  # an empty keyword query empties the sparse route, leaving the vector route
            settings.rag_recall_candidates, settings.rag_rerank_candidates, settings.rag_rrf_k,
        )
        found = found[:top_k]
    else:
        searcher = Searcher(
            rag.store, rag.embedder, rag.searcher._reranker if rerank else None,
            recall=settings.rag_recall_candidates, candidates=settings.rag_rerank_candidates,
            rrf_k=settings.rag_rrf_k, min_score=None,
        )
        found = (await searcher.search(question["q"], [kb_name], top_k)).hits
    spans = [Span(question, hit.path, hit.content) for hit in found]
    return Outcome(spans, found[0].score if found else 0.0)


CONFIGURATIONS = {
    "dense only": dict(dense_only=True, rerank=False),
    "hybrid (RRF)": dict(dense_only=False, rerank=False),
    "hybrid + rerank": dict(dense_only=False, rerank=True),
}


async def evaluate(kb_name: str, questions: list[dict], top_k: int) -> dict[str, dict[str, float | None]]:
    rag = build_rag()
    answerable = [q for q in questions if q["expect"] != "none"]
    unanswerable = [q for q in questions if q["expect"] == "none"]
    table: dict[str, dict[str, float | None]] = {}
    for label, options in CONFIGURATIONS.items():
        outcomes = [await run_configuration(rag, kb_name, q, top_k=top_k, **options) for q in answerable]
        n = max(len(answerable), 1)
        none_scores = [
            (await run_configuration(rag, kb_name, q, top_k=top_k, **options)).top_score for q in unanswerable
        ]
        table[label] = {
            "hit@1": sum(hits_within(q, o.spans, 1) for q, o in zip(answerable, outcomes)) / n,
            "hit@5": sum(hits_within(q, o.spans, 5) for q, o in zip(answerable, outcomes)) / n,
            "mrr": statistics.fmean(reciprocal_rank(q, o.spans) for q, o in zip(answerable, outcomes)) if outcomes else 0.0,
            "top score on unanswerable": statistics.fmean(none_scores) if none_scores else None,
        }
    return table


def print_table(table: dict[str, dict[str, float | None]]) -> None:
    print(f"{'configuration':18s} {'hit@1':>6s} {'hit@5':>6s} {'MRR':>6s}  {'mean top score on unanswerable':>30s}")
    for label, row in table.items():
        none = row["top score on unanswerable"]
        shown = f"{none:.3f}" if isinstance(none, float) else "-"
        print(f"{label:18s} {row['hit@1']:6.3f} {row['hit@5']:6.3f} {row['mrr']:6.3f}  {shown:>30s}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure retrieval quality on a knowledge base")
    parser.add_argument("--kb", required=True)
    parser.add_argument("--questions", required=True, type=Path)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args(argv)
    table = asyncio.run(evaluate(args.kb, load_questions(args.questions), args.top_k))
    print_table(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
