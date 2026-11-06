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
    with pytest.raises(RuntimeError, match="RAG_ENABLED") as exc:
        build_rag()
    assert "embedder and count_tokens" in str(exc.value)


def test_the_error_names_only_what_is_actually_missing():
    with pytest.raises(RuntimeError) as exc:
        build_rag(embedder=HashEmbedder())
    assert "missing count_tokens:" in str(exc.value) and "embedder" not in str(exc.value).split(":")[0]
    with pytest.raises(RuntimeError) as exc:
        build_rag(count_tokens=len)
    assert "missing embedder:" in str(exc.value)


def test_importing_the_app_does_not_load_torch_or_the_pdf_stack():
    code = (
        "import sys, app.main; "
        "bad = [m for m in ('torch', 'sentence_transformers', 'transformers') if m in sys.modules]; "
        "print(bad); sys.exit(1 if bad else 0)"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr


def test_the_default_source_factory_gives_every_knowledge_base_its_own_git_checkout(tmp_path, monkeypatch):
    """The default factory is what production uses; tests normally inject their own, so pin it here."""
    import uuid

    from app.config import settings
    from app.rag.ingest.sources import GitSource
    from app.rag.persistence.store import KbRef

    monkeypatch.setattr(settings, "rag_clone_dir", str(tmp_path))
    rag = build_rag(embedder=HashEmbedder(), reranker=None, count_tokens=len)
    factory = rag.syncer._source_factory

    def ref(subdir):
        return KbRef(uuid.uuid4(), "k", "d", "https://example.com/r.git", "main", subdir, "m", 1024, None)

    a, b = factory(ref("a")), factory(ref("b"))
    assert isinstance(a, GitSource) and isinstance(b, GitSource)
    assert a.workdir != b.workdir  # same repository, same branch: still separate checkouts
    same = ref("a")
    assert factory(same).workdir == factory(same).workdir  # but stable for one knowledge base
