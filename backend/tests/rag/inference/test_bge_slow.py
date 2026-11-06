"""Tests with the REAL models. Skipped unless run with `-m slow` and the models are downloaded
(backend/scripts/download_models.py)."""

import asyncio
from pathlib import Path

import pytest

from app.config import settings

pytestmark = pytest.mark.slow

MODELS = Path(settings.rag_model_dir)


@pytest.fixture(scope="module")
def models_present():
    needed = [MODELS / "bge-m3" / "pytorch_model.bin", MODELS / "bge-reranker-v2-m3" / "model.safetensors"]
    if not all(p.is_file() for p in needed):
        pytest.skip("models are not downloaded; run backend/scripts/download_models.py")


@pytest.fixture(scope="module")
def embedder(models_present):
    from app.rag.inference.device import resolve_device
    from app.rag.inference.embedding import BgeM3Embedder

    return BgeM3Embedder(str(MODELS / "bge-m3"), resolve_device("auto"), 8)


@pytest.fixture(scope="module")
def reranker(models_present):
    from app.rag.inference.device import resolve_device
    from app.rag.inference.rerank import BgeReranker

    return BgeReranker(str(MODELS / "bge-reranker-v2-m3"), resolve_device("auto"))


def cos(a, b):
    return sum(x * y for x, y in zip(a, b))


async def test_embeddings_are_normalised_1024_dimensional_and_rank_by_meaning(embedder):
    docs = ["回滚部署的步骤:执行 kubectl rollout undo", "how to roll back a deployment", "今天天气很好,适合出去散步"]
    vectors = await embedder.embed_documents(docs)
    query = await embedder.embed_query("怎么回滚部署")
    assert [len(v) for v in vectors] == [1024, 1024, 1024] and len(query) == 1024
    assert all(abs(cos(v, v) - 1.0) < 1e-3 for v in vectors)  # normalised: cosine == inner product
    assert cos(query, vectors[0]) > cos(query, vectors[2])  # Chinese match beats the unrelated sentence
    assert cos(query, vectors[1]) > cos(query, vectors[2])  # and so does the ENGLISH match: cross-lingual


async def test_embedding_is_deterministic_and_batch_independent(embedder):
    one = await embedder.embed_query("同一句话")
    batch = await embedder.embed_documents(["同一句话", "另一句话", "第三句话"])
    again = await embedder.embed_query("同一句话")
    assert cos(one, again) > 0.9999 and cos(one, batch[0]) > 0.999  # batching/padding must not change a vector


async def test_reranker_scores_are_probabilities_and_order_by_relevance(reranker):
    scores = await reranker.rerank(
        "怎么回滚部署",
        ["回滚部署的步骤:执行 kubectl rollout undo 恢复到上一个版本", "今天天气很好,适合出去散步,公园里有很多人"],
    )
    assert all(0.0 <= s <= 1.0 for s in scores) and all(type(s) is float for s in scores)
    assert scores[0] > 0.8 and scores[1] < 0.2


async def test_reranker_is_cross_lingual(reranker):
    scores = await reranker.rerank("how do I roll back a release", ["执行 kubectl rollout undo 回滚发布", "监控面板的使用方法"])
    assert scores[0] > scores[1]


async def test_the_reranker_reads_the_whole_passage_up_to_512_tokens(reranker):
    """With max_length=128 the relevant sentence at the END of a long passage was cut off: score 0.0001 instead of 0.90."""
    tail = "无关内容。" * 120 + "回滚部署的步骤:执行 kubectl rollout undo 恢复到上一个版本"
    (score,) = await reranker.rerank("怎么回滚部署", [tail])
    assert score > 0.5, f"score {score:.4f}: the answer at the end of the passage was not seen"


async def test_a_passage_longer_than_the_models_limit_does_not_crash(reranker):
    scores = await reranker.rerank("回滚", ["这是一个很长的段落。" * 400, "短"])
    assert len(scores) == 2 and all(0.0 <= s <= 1.0 for s in scores)


async def test_inference_does_not_block_the_event_loop(embedder):
    ticks = 0

    async def heartbeat():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    task = asyncio.create_task(heartbeat())
    await embedder.embed_documents(["一段需要计算向量的比较长的中文文本。" * 20] * 24)
    task.cancel()
    assert ticks >= 5, f"the event loop only ticked {ticks} times while the model ran"


def test_the_token_counter_matches_the_embedding_models_tokenizer(models_present):
    from app.rag.inference.tokenizer import make_token_counter

    count = make_token_counter(str(MODELS / "bge-m3"))
    assert count("") == 0
    zh, en = count("第3步需要先检查配置是否正确,然后再继续执行后续的操作流程。"), count("This is a plain English sentence about deployment rollback.")
    assert 12 <= zh <= 28 and 10 <= en <= 20
    assert count("a" * 5000) > 100  # no truncation at the model's limit


async def test_the_chunker_keeps_every_index_text_within_the_rerankers_limit_with_the_real_tokenizer(models_present):
    """The point of the whole chunk-size design: with the real token counter nothing exceeds 512 tokens."""
    from app.rag.ingest.chunking import ChunkConfig, chunk_markdown
    from app.rag.inference.tokenizer import make_token_counter

    count = make_token_counter(str(MODELS / "bge-m3"))
    text = Path.home().joinpath("Documents/obsidian/sagent/2026-11-05-rag-knowledge-base-design.md")
    if not text.exists():
        pytest.skip("design document not available")
    cfg = ChunkConfig(settings.rag_chunk_target_tokens, settings.rag_chunk_max_tokens, settings.rag_chunk_overlap_tokens, settings.rag_min_chunk_chars)
    for title, tags in (("T", ""), ("一个比较长的文档标题" * 4, "运维 部署 回滚 监控 告警")):
        chunks = chunk_markdown(text.read_text(encoding="utf-8"), title, tags, cfg, count).chunks
        worst = max(count(c.index_text) for c in chunks)
        assert worst <= cfg.max_tokens, f"a chunk has {worst} tokens, the reranker truncates beyond {cfg.max_tokens}"


async def test_normalisation_and_sigmoid_do_not_depend_on_the_library_defaults(embedder, reranker):
    """bge-m3 ships its own Normalize module and this CrossEncoder defaults to Sigmoid today; both settings in
    our adapters are explicit so a library or model update cannot silently change the score range."""
    import inspect

    from app.rag.inference import embedding, rerank

    assert "normalize_embeddings=True" in inspect.getsource(embedding.BgeM3Embedder._encode)
    assert "Sigmoid" in inspect.getsource(rerank.BgeReranker._load)
    # and the observable contract holds with the real models
    (v,) = await embedder.embed_documents(["任意文本"])
    assert abs(sum(x * x for x in v) - 1.0) < 1e-3
    scores = await reranker.rerank("q", ["a", "b"])
    assert all(0.0 <= s <= 1.0 for s in scores)
