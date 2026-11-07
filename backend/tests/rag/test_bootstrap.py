import subprocess
import sys

import pytest

from app.rag.bootstrap import build_rag
from tests.rag.fakes import HashEmbedder, KeywordReranker


def fill_models(root, only=None, truncate=None):
    """Create files with the sizes of the real models, sparse, so no disk is used. `truncate` shrinks one."""
    from app.rag.bootstrap import REQUIRED_MODEL_FILES

    for name, files in REQUIRED_MODEL_FILES.items():
        if only is not None and name not in only:
            continue
        (root / name).mkdir(parents=True, exist_ok=True)
        for file, size in files.items():
            with open(root / name / file, "wb") as handle:
                handle.truncate(size // 2 if truncate == f"{name}/{file}" else size)


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

    fill_models(tmp_path, only=("bge-m3",))
    monkeypatch.setattr(settings, "rag_model_dir", str(tmp_path))
    with pytest.raises(RuntimeError) as exc:
        build_rag()
    assert "bge-m3/" not in str(exc.value)  # the embedder files are all there
    assert "bge-reranker-v2-m3/model.safetensors" in str(exc.value)


def test_without_a_reranker_the_reranker_files_are_not_required(tmp_path, monkeypatch):
    from app.config import settings

    fill_models(tmp_path, only=("bge-m3",))
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

    fill_models(tmp_path)
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


def test_a_truncated_weight_file_is_refused_at_start_up_not_at_the_first_query(tmp_path, monkeypatch):
    """A download interrupted at 50% leaves the file in place; existence alone would let it through."""
    from app.config import settings

    fill_models(tmp_path, truncate="bge-m3/pytorch_model.bin")
    monkeypatch.setattr(settings, "rag_model_dir", str(tmp_path))
    with pytest.raises(RuntimeError) as exc:
        build_rag()
    msg = str(exc.value)
    assert "incomplete model files" in msg and "bge-m3/pytorch_model.bin" in msg and "download_models.py" in msg
    assert "of 2271145830 bytes" in msg
    assert "model files not found" not in msg  # it exists; it is incomplete


def test_a_truncated_reranker_file_is_only_a_problem_when_a_reranker_is_wanted(tmp_path, monkeypatch):
    from app.config import settings

    fill_models(tmp_path, truncate="bge-reranker-v2-m3/model.safetensors")
    monkeypatch.setattr(settings, "rag_model_dir", str(tmp_path))
    with pytest.raises(RuntimeError, match="bge-reranker-v2-m3/model.safetensors"):
        build_rag()
    assert build_rag(reranker=None).searcher is not None


def test_files_a_hair_below_the_recorded_size_are_accepted(tmp_path, monkeypatch):
    from app.config import settings
    from app.rag.bootstrap import REQUIRED_MODEL_FILES

    fill_models(tmp_path)
    weights = tmp_path / "bge-m3" / "pytorch_model.bin"
    with open(weights, "r+b") as handle:
        handle.truncate(REQUIRED_MODEL_FILES["bge-m3"]["pytorch_model.bin"] - 1000)  # an upstream re-export
    monkeypatch.setattr(settings, "rag_model_dir", str(tmp_path))
    assert build_rag().embedder is not None


def test_an_unusable_device_fails_at_start_up_with_the_setting_named(tmp_path, monkeypatch):
    """The reranker's errors are absorbed by a fall-back, so a wrong device would switch it off silently."""
    import sys
    import types

    from app.config import settings

    fill_models(tmp_path)
    monkeypatch.setattr(settings, "rag_model_dir", str(tmp_path))
    monkeypatch.setattr(settings, "rag_device", "cuda")
    torch = types.SimpleNamespace(
        cuda=types.SimpleNamespace(is_available=lambda: False),
        backends=types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: False)),
    )
    monkeypatch.setitem(sys.modules, "torch", torch)
    with pytest.raises(RuntimeError, match="RAG_DEVICE='cuda' but CUDA is not available"):
        build_rag()


async def test_warm_up_loads_both_models_through_their_own_hook():
    """Each model's first load takes ~85 s; start-up pays it so no user does."""
    calls = []

    class FakeEmbedder(HashEmbedder):
        async def warm_up(self):
            calls.append("embedder")

    class FakeReranker:
        async def rerank(self, query, docs):
            return [0.5] * len(docs)

        async def warm_up(self):
            calls.append("reranker")

    from app.rag.bootstrap import warm_up

    await warm_up(build_rag(embedder=FakeEmbedder(), reranker=FakeReranker(), count_tokens=len))
    assert calls == ["embedder", "reranker"]


async def test_warm_up_tolerates_a_component_without_the_hook():
    from app.rag.bootstrap import warm_up
    from tests.rag.fakes import ReverseReranker  # no warm_up

    await warm_up(build_rag(embedder=HashEmbedder(), reranker=ReverseReranker(), count_tokens=len))


async def test_without_a_reranker_only_the_embedder_is_warmed():
    calls = []

    class FakeEmbedder(HashEmbedder):
        async def warm_up(self):
            calls.append("embedder")

    from app.rag.bootstrap import warm_up

    await warm_up(build_rag(embedder=FakeEmbedder(), reranker=None, count_tokens=len))
    assert calls == ["embedder"]


def test_the_rerank_timeout_tolerates_a_cold_load_and_start_up_warms_by_default():
    from app.config import Settings

    fresh = Settings()  # defaults, not whatever .env says
    assert fresh.rag_rerank_timeout_s >= 120  # a cold model needs ~85 s to load
    assert fresh.rag_load_on_start is True
