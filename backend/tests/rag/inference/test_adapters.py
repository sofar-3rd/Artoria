"""The model adapters without loading a model: what they do before and around the heavy part."""

import sys

import pytest

from app.rag.core.ports import Embedder, Reranker
from app.rag.inference.embedding import BgeM3Embedder
from app.rag.inference.rerank import BgeReranker
from app.rag.inference.tokenizer import make_token_counter


def test_constructing_the_adapters_loads_nothing():
    emb = BgeM3Embedder("/does/not/exist", "cpu", 8)
    rr = BgeReranker("/does/not/exist", "cpu")
    count = make_token_counter("/does/not/exist")
    assert emb._model is None and rr._model is None and callable(count)
    assert not {"torch", "sentence_transformers", "transformers"} & set(sys.modules) - _already_loaded


_already_loaded = {m for m in ("torch", "sentence_transformers", "transformers") if m in sys.modules}


def test_the_adapters_satisfy_the_ports():
    emb: Embedder = BgeM3Embedder("x")
    rr: Reranker = BgeReranker("x")
    assert emb.model == "BAAI/bge-m3" and emb.dim == 1024
    assert callable(emb.embed_documents) and callable(emb.embed_query) and callable(rr.rerank)


async def test_empty_input_does_not_load_the_model():
    emb, rr = BgeM3Embedder("/does/not/exist"), BgeReranker("/does/not/exist")
    assert await emb.embed_documents([]) == []
    assert await rr.rerank("q", []) == []
    assert emb._model is None and rr._model is None


async def test_a_missing_model_directory_fails_with_a_clear_error_on_first_use():
    with pytest.raises(Exception) as exc:
        await BgeM3Embedder("/does/not/exist").embed_query("hello")
    assert "does/not/exist" in str(exc.value) or "not exist" in str(exc.value).lower() or "not a valid" in str(exc.value).lower()


def test_the_embedder_uses_the_configured_model_name_as_the_index_identity():
    # Syncer/Searcher compare this string with what a knowledge base was indexed with.
    from app.config import settings

    assert BgeM3Embedder.model == settings.rag_embed_model and BgeM3Embedder.dim == settings.rag_embed_dim


def test_clean_replaces_lone_surrogates_and_bounds_the_length():
    from app.rag.inference.text import MAX_DOCUMENT_CHARS, clean

    assert clean("abc\ud800def") == "abc?def"  # a lone surrogate used to raise a bare TypeError in the tokenizer
    assert clean("emoji \U0001F600 stays") == "emoji \U0001F600 stays"  # real characters, emoji included, are untouched
    assert clean("") == "" and clean("正常文本") == "正常文本" and clean("a\x00b") == "a\x00b"
    assert len(clean("x" * 100_000)) == MAX_DOCUMENT_CHARS
    assert len(clean("x" * 100_000, 50)) == 50  # the limit is a parameter


def test_the_document_cap_is_far_above_what_a_512_token_chunk_can_contain():
    from app.rag.inference.text import MAX_DOCUMENT_CHARS, MAX_QUERY_CHARS

    assert MAX_DOCUMENT_CHARS >= 512 * 4  # even plain English at ~4 characters per token: it never bites a chunk
    assert MAX_QUERY_CHARS <= MAX_DOCUMENT_CHARS // 2  # a query is bounded much tighter: it is the unbounded input


async def test_adapters_clean_their_input_before_it_reaches_the_model(monkeypatch):
    seen = {}
    emb = BgeM3Embedder("x")
    monkeypatch.setattr(emb, "_encode", lambda texts: seen.setdefault("emb", texts) and [[0.0]] * len(texts))
    await emb.embed_documents(["a\ud800b", "y" * 50_000])
    assert seen["emb"][0] == "a?b" and len(seen["emb"][1]) == 8000
    rr = BgeReranker("x")
    monkeypatch.setattr(rr, "_score", lambda q, docs: seen.update(q=q, docs=docs) or [0.5] * len(docs))
    await rr.rerank("q\ud800", ["d" * 50_000])
    assert seen["q"] == "q?" and len(seen["docs"][0]) == 8000


async def test_a_query_is_capped_much_lower_than_document_text(monkeypatch):
    """The 8,000-character document cap still held the inference thread for ~5 s; a query gets 2,000 (0.3 s)."""
    seen = {}
    emb = BgeM3Embedder("x")
    monkeypatch.setattr(emb, "_encode", lambda texts: seen.update(texts=texts) or [[0.0]] * len(texts))
    await emb.embed_query("很" * 50_000)
    assert len(seen["texts"][0]) == 2000
    await emb.embed_documents(["很" * 50_000])
    assert len(seen["texts"][0]) == 8000  # document text keeps its own, higher, safety net
    rr = BgeReranker("x")
    monkeypatch.setattr(rr, "_score", lambda q, docs: seen.update(q=q, docs=docs) or [0.5] * len(docs))
    await rr.rerank("很" * 50_000, ["很" * 50_000])
    assert len(seen["q"]) == 2000 and len(seen["docs"][0]) == 8000
