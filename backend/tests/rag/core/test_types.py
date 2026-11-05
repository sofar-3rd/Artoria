import dataclasses

import pytest

from app.config import settings
from app.rag.core.errors import RagError, UnknownKnowledgeBase
from app.rag.core.types import Chunk, Snapshot


def test_chunk_is_frozen():
    c = Chunk(0, "A > B", "body", "T > A > B\nbody", 0, 4)
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.idx = 1


def test_snapshot_read_delegates_to_reader():
    snap = Snapshot("rev1", {"a.md": "sha"}, lambda p: p.encode())
    assert snap.read("a.md") == b"a.md"


def test_unknown_kb_error_lists_known_names():
    err = UnknownKnowledgeBase("zzz", ["docs", "ops"])
    assert isinstance(err, RagError)
    assert "zzz" in str(err) and "docs" in str(err) and "ops" in str(err)


def test_rag_settings_defaults():
    assert settings.rag_embed_dim == 1024
    assert settings.rag_rerank_candidates == 20
    assert settings.rag_top_k == 5
    assert settings.rag_min_rerank_score is None
    assert settings.rag_chunk_target_tokens == 400
    assert settings.rag_chunk_max_tokens == 512
    assert settings.rag_chunk_overlap_tokens == 50
