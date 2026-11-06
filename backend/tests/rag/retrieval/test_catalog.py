import uuid

import pytest

from app.db import SessionLocal, engine
from app.rag.core.errors import DocumentNotFound
from app.rag.core.types import Chunk
from app.rag.persistence.store import Store
from app.rag.retrieval.catalog import Catalog
from tests.rag.fakes import HashEmbedder

emb = HashEmbedder()


@pytest.fixture(autouse=True)
async def _dispose():
    yield
    await engine.dispose()


async def seed(store, text="0123456789" * 3):
    kb = await store.create_kb(f"kb-{uuid.uuid4().hex[:6]}", "docs about things", "dir:/x", "main", "", emb.model, emb.dim)
    chunks = [Chunk(0, "H", text, f"T\n{text}", 0, len(text))]
    await store.replace_document(kb.id, "a.md", "A", text, "s", chunks, await emb.embed_documents([chunks[0].index_text]))
    hits = await store.hybrid_candidates([kb.id], text, await emb.embed_query(text), 5, 5, 60)
    return kb, hits[0].doc_id


async def test_list_kbs_reports_document_count_and_description():
    store = Store(SessionLocal)
    kb, _ = await seed(store)
    info = [i for i in await Catalog(store).list_kbs() if i.name == kb.name][0]
    assert info.doc_count == 1 and info.description == "docs about things"


async def test_read_document_pages_through_the_text():
    store = Store(SessionLocal)
    _, doc_id = await seed(store)
    cat = Catalog(store)
    first = await cat.read_document(doc_id, 0, 10)
    assert (first.text, first.has_more, first.total_chars) == ("0123456789", True, 30)
    last = await cat.read_document(doc_id, 20, 100)
    assert (last.text, last.has_more) == ("0123456789", False)


async def test_read_document_clamps_offset_and_limit():
    store = Store(SessionLocal)
    _, doc_id = await seed(store, "x" * 25000)
    cat = Catalog(store)
    assert (await cat.read_document(doc_id, -5, 10)).offset == 0
    assert len((await cat.read_document(doc_id, 0, 10**9)).text) == 20000  # MAX_PAGE_CHARS
    assert len((await cat.read_document(doc_id, 0, 0)).text) == 1  # limit < 1 becomes 1, so paging always advances


async def test_read_document_default_page_is_6000_chars():
    store = Store(SessionLocal)
    _, doc_id = await seed(store, "y" * 9000)
    page = await Catalog(store).read_document(doc_id)
    assert len(page.text) == 6000 and page.has_more is True


@pytest.mark.parametrize("bad", ["not-a-uuid", "", "   ", "123", str(uuid.uuid4())])
async def test_read_document_unknown_or_malformed_id(bad):
    with pytest.raises(DocumentNotFound):
        await Catalog(Store(SessionLocal)).read_document(bad)


async def test_read_document_tolerates_surrounding_whitespace_in_the_id():
    store = Store(SessionLocal)
    _, doc_id = await seed(store)
    assert (await Catalog(store).read_document(f"  {doc_id}\n", 0, 5)).text == "01234"
