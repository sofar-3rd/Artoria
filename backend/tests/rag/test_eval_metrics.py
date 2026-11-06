"""The evaluation metrics: they decide whether reranking stays on, so they are tested like any other code."""

from pathlib import Path

import pytest
import yaml

from scripts.eval_retrieval import Span, hits_within, is_answer, load_questions, reciprocal_rank

Q = {"q": "how to roll back", "expect": "ops/rollback.md", "must": "rollout undo"}


def span(path: str, content: str, question: dict = Q) -> Span:
    return Span(question, path, content)


def test_a_passage_answers_only_when_document_and_phrase_match():
    assert is_answer(Q, span("ops/rollback.md", "run kubectl rollout undo"))
    assert not is_answer(Q, span("ops/rollback.md", "monitoring only"))  # right file, wrong passage
    assert not is_answer(Q, span("other.md", "run kubectl rollout undo"))  # right text, wrong file


def test_the_phrase_is_optional_and_case_insensitive():
    without = {"q": "q", "expect": "a.md"}
    assert is_answer(without, span("a.md", "anything", without))
    assert is_answer(Q, span("ops/rollback.md", "RUN KUBECTL ROLLOUT UNDO"))


def test_an_unanswerable_question_never_has_an_answer():
    q = {"q": "capital of France", "expect": "none"}
    paris = span("a.md", "Paris is the capital of France", q)
    assert not is_answer(q, paris)
    assert not hits_within(q, [paris], 5) and reciprocal_rank(q, [paris]) == 0.0


def test_hit_at_k_counts_a_later_passage_only_within_k():
    spans = [span("a.md", "nothing"), span("ops/rollback.md", "rollout undo here")]
    assert not hits_within(Q, spans, 1)
    assert hits_within(Q, spans, 2)


def test_reciprocal_rank_is_one_over_the_first_answering_position():
    spans = [span("a.md", "x"), span("b.md", "y"), span("ops/rollback.md", "rollout undo")]
    assert reciprocal_rank(Q, spans) == pytest.approx(1 / 3)
    assert reciprocal_rank(Q, [spans[2], spans[0]]) == 1.0
    assert reciprocal_rank(Q, spans[:2]) == 0.0


def test_two_chunks_of_the_same_document_are_judged_separately():
    """The answering chunk of a document is not always its highest ranked one."""
    spans = [span("ops/rollback.md", "intro"), span("ops/rollback.md", "run kubectl rollout undo")]
    assert not hits_within(Q, spans, 1) and hits_within(Q, spans, 2)


def test_the_question_file_is_validated(tmp_path):
    good = tmp_path / "q.yaml"
    good.write_text(yaml.safe_dump([{"q": "a", "expect": "a.md"}, {"q": "b", "expect": "none"}]), encoding="utf-8")
    assert len(load_questions(good)) == 2
    for bad in ([], [{"q": "a"}], [{"expect": "a.md"}], "not a list"):
        path = tmp_path / "bad.yaml"
        path.write_text(yaml.safe_dump(bad), encoding="utf-8")
        with pytest.raises(SystemExit):
            load_questions(path)


def test_the_tracked_question_file_is_well_formed_and_every_phrase_is_distinctive():
    """The evaluation set is only meaningful if every answerable question carries a `must` phrase."""
    questions = load_questions(Path(__file__).resolve().parents[2] / "eval" / "questions.yaml")
    answerable = [q for q in questions if q["expect"] != "none"]
    assert len(answerable) >= 10 and len(questions) > len(answerable)  # answerable questions plus "none" ones
    for q in answerable:
        assert q.get("must"), f"question without a distinguishing phrase: {q['q']}"
