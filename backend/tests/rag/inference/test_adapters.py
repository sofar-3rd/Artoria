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
