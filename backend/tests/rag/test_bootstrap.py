import subprocess
import sys

import pytest

from app.rag.bootstrap import build_rag
from tests.rag.fakes import HashEmbedder, KeywordReranker


def test_build_rag_with_injected_components_does_not_load_models():
    rag = build_rag(embedder=HashEmbedder(), reranker=KeywordReranker(), count_tokens=len)
    assert rag.catalog and rag.searcher and rag.syncer and rag.store


def test_reranker_is_optional():
    rag = build_rag(embedder=HashEmbedder(), reranker=None, count_tokens=len)
    assert rag.searcher is not None


def test_without_an_embedder_the_error_says_what_to_do():
    with pytest.raises(RuntimeError, match="RAG_ENABLED"):
        build_rag()


def test_importing_the_app_does_not_load_torch_or_the_pdf_stack():
    code = (
        "import sys, app.main; "
        "bad = [m for m in ('torch', 'sentence_transformers', 'transformers') if m in sys.modules]; "
        "print(bad); sys.exit(1 if bad else 0)"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr
