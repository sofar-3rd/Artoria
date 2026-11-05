import uuid

import pytest
from sqlalchemy import text

from app.db import SessionLocal, engine
from app.rag.persistence import fts
from app.rag.persistence.models import ChunkRow, Document, KnowledgeBase


@pytest.fixture(autouse=True)
async def _dispose():
    yield
    await engine.dispose()


def test_fts_sql_fragments():
    assert fts.tsvector_sql("t") == "to_tsvector('jiebacfg', :t)"
    assert "plainto_tsquery('jiebacfg', :q)" in fts.tsquery_or_sql("q")
    assert "' | '" in fts.tsquery_or_sql("q")


async def test_cascade_delete_and_vector_roundtrip():
    async with SessionLocal() as s:
        kb = KnowledgeBase(name=f"kb-{uuid.uuid4().hex[:6]}", description="d",
                           repo_url="dir:/x", embed_model="m", embed_dim=1024)
        s.add(kb); await s.flush()
        doc = Document(kb_id=kb.id, path="a.md", title="A", content="body", content_sha="s")
        s.add(doc); await s.flush()
        s.add(ChunkRow(doc_id=doc.id, kb_id=kb.id, idx=0, heading_path="", start_char=0,
                       end_char=4, content="body", embedding=[0.1] * 1024))
        await s.flush()
        await s.execute(text("UPDATE chunks SET tsv = " + fts.tsvector_sql("t")), {"t": "回滚部署"})
        n = (await s.execute(text("SELECT count(*) FROM chunks WHERE tsv @@ to_tsquery('jiebacfg','回滚')"))).scalar()
        assert n == 1
        await s.delete(kb); await s.commit()
        left = (await s.execute(text("SELECT count(*) FROM chunks"))).scalar()
        assert left == 0
