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


def test_missing_model_files_fail_at_build_time_with_the_fix_in_the_message(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "rag_model_dir", str(tmp_path / "no-models-here"))
    with pytest.raises(RuntimeError) as exc:
        build_rag()
    msg = str(exc.value)
    assert "model files not found" in msg and "download_models.py" in msg
    assert "bge-m3/pytorch_model.bin" in msg and "bge-reranker-v2-m3/model.safetensors" in msg


def test_a_partial_download_is_reported_file_by_file(tmp_path, monkeypatch):
    from app.config import settings

    (tmp_path / "bge-m3").mkdir()
    for name in ("config.json", "pytorch_model.bin", "tokenizer.json"):
        (tmp_path / "bge-m3" / name).write_bytes(b"x")
    monkeypatch.setattr(settings, "rag_model_dir", str(tmp_path))
    with pytest.raises(RuntimeError) as exc:
        build_rag()
    assert "bge-m3/" not in str(exc.value)  # the embedder files are all there
    assert "bge-reranker-v2-m3/model.safetensors" in str(exc.value)


def test_without_a_reranker_the_reranker_files_are_not_required(tmp_path, monkeypatch):
    from app.config import settings

    (tmp_path / "bge-m3").mkdir()
    for name in ("config.json", "pytorch_model.bin", "tokenizer.json"):
        (tmp_path / "bge-m3" / name).write_bytes(b"x")
    monkeypatch.setattr(settings, "rag_model_dir", str(tmp_path))
    rag = build_rag(reranker=None)  # models are built lazily, nothing is loaded here
    assert rag.searcher is not None and rag.embedder.model == "BAAI/bge-m3"


def test_an_explicit_none_reranker_is_respected_not_replaced_by_the_default():
    rag = build_rag(embedder=HashEmbedder(), reranker=None, count_tokens=len)
    assert rag.searcher._reranker is None


def test_default_components_are_the_real_models_built_lazily(tmp_path, monkeypatch):
    from app.config import settings
    from app.rag.inference.embedding import BgeM3Embedder
    from app.rag.inference.rerank import BgeReranker

    for name, files in {"bge-m3": ("config.json", "pytorch_model.bin", "tokenizer.json"),
                        "bge-reranker-v2-m3": ("config.json", "model.safetensors", "tokenizer.json")}.items():
        (tmp_path / name).mkdir()
        for f in files:
            (tmp_path / name / f).write_bytes(b"x")
    monkeypatch.setattr(settings, "rag_model_dir", str(tmp_path))
    rag = build_rag()
    assert isinstance(rag.embedder, BgeM3Embedder) and isinstance(rag.searcher._reranker, BgeReranker)
    assert rag.embedder._model is None and rag.searcher._reranker._model is None  # nothing was loaded


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
