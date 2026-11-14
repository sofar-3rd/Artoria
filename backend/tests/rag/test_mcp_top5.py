import importlib.util

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("ragas") is None, reason="Requires the optional eval dependency group"
)


async def test_top5_groups_use_reference_count_and_macro_average():
    from scripts.eval_mcp_top5 import grouped_scores

    records = [
        dict(method="rerank", references=["a"], ranked_ids=["a"], error=None),
        dict(method="rerank", references=["b"], ranked_ids=["x", "b"], error=None),
        dict(method="rerank", references=["a", "b"], ranked_ids=["a", "x"], error=None),
        dict(method="rerank", references=["a", "b", "c"], ranked_ids=["x", "a", "b"], error=None),
    ]
    rows = {r["correct_tools"]: r for r in await grouped_scores(records)}
    assert rows[1]["questions"] == 2
    assert rows[1]["recall_at_5"] == 1
    assert rows[1]["mrr_at_5"] == 0.75
    assert rows[2]["recall_at_5"] == 0.5 and rows[2]["mrr_at_5"] == 1
    assert rows[3]["recall_at_5"] == pytest.approx(2 / 3)
    assert rows[3]["mrr_at_5"] == 0.5


async def test_top5_scores_ignore_matches_beyond_five_and_report_failures():
    from scripts.eval_mcp_top5 import grouped_scores

    rows = await grouped_scores([
        dict(method="rerank", references=["a"], ranked_ids=["1", "2", "3", "4", "5", "a"], error="failed"),
    ])
    assert rows[0]["recall_at_5"] == rows[0]["mrr_at_5"] == rows[0]["hit_at_5"] == 0
    assert rows[0]["rerank_failures"] == 1


async def test_variant_database_rejects_business_database():
    from scripts.eval_mcp_top5 import open_variant_database

    with pytest.raises(ValueError, match="exactly sagent_rag_eval"):
        await open_variant_database("postgresql://localhost/sagent")
