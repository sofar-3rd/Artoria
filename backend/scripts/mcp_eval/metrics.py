import math
import os
from functools import lru_cache

os.environ["RAGAS_DO_NOT_TRACK"] = "true"


@lru_cache(maxsize=1)
def _metrics():
    from ragas import SingleTurnSample
    from ragas.metrics import IDBasedContextPrecision, IDBasedContextRecall

    return SingleTurnSample, IDBasedContextPrecision(), IDBasedContextRecall()


async def score_ranking(ranked: list[str], references: list[str], k: int) -> dict:
    if k < 1 or not references or len(ranked) != len(set(ranked)):
        raise ValueError("positive k, non-empty references and unique ranked tool IDs required")
    Sample, precision, recall = _metrics()
    ids = ranked[:k]
    sample = Sample(retrieved_context_ids=ids, reference_context_ids=references)
    p = float(await precision.single_turn_ascore(sample)) if ids else float("nan")
    r = float(await recall.single_turn_ascore(sample))
    rr = next((1 / (i + 1) for i, item in enumerate(ids) if item in references), 0.0)
    return {"ragas_precision": p, "precision": 0.0 if math.isnan(p) else p,
            "recall": r, "hit": float(rr > 0), "mrr": rr, "returned": len(ids)}
