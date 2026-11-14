import asyncio

import pytest

from app.config import settings
from app.rag.bootstrap import build_rag
from app.rag.ingest.sources import DirSource
from tests.rag.fakes import HashEmbedder, KeywordReranker

TOKEN = "s3cret-token"
H = {"X-Admin-Token": TOKEN}
REMOTE = "https://example.com/org/docs.git"


@pytest.fixture(autouse=True)
def admin_token(monkeypatch):
    monkeypatch.setattr(settings, "rag_admin_token", TOKEN)
    monkeypatch.setattr(settings, "rag_local_root", "")


def fake_rag(tmp_path):
    return build_rag(
        embedder=HashEmbedder(), reranker=KeywordReranker(), count_tokens=len,
        source_factory=lambda kb: DirSource(tmp_path),
    )


def body(**kw):
    return {"name": "docs-1", "description": "d", "repo_url": REMOTE, **kw}


async def seeded_kb(client, name, tmp_path, monkeypatch):
    """Create two knowledge bases with one document each, using real syncing."""
    monkeypatch.setattr(settings, "rag_local_root", str(tmp_path))
    (tmp_path / "a.md").write_text("# A\n\n" + "alpha " * 400 + "\n", encoding="utf-8")
    await client.post("/api/kbs", json=body(name=name, repo_url=f"dir:{tmp_path}"), headers=H)
    await client.post(f"/api/kbs/{name}/sync", headers=H)
    await wait_synced(client, name)


async def wait_synced(client, name, tries=100):
    for _ in range(tries):
        info = (await client.get(f"/api/kbs/{name}")).json()
        if not info["running"]:
            return info
        await asyncio.sleep(0.05)
    raise AssertionError("sync did not finish")


async def test_document_list_has_ids_paths_titles_and_lengths(running_app, tmp_path, monkeypatch):
    async with running_app([], rag=fake_rag(tmp_path)) as (_, c):
        await seeded_kb(c, "docs-1", tmp_path, monkeypatch)
        r = await c.get("/api/kbs/docs-1/documents")
        assert r.status_code == 200
        docs = r.json()
        assert len(docs) == 1
        assert docs[0]["path"] == "a.md" and docs[0]["title"] == "A"
        assert docs[0]["chars"] == len("# A\n\n" + "alpha " * 400 + "\n")
        assert docs[0]["doc_id"]  # a usable id, not an empty placeholder


async def test_document_page_is_bounded_and_reports_whether_more_remains(running_app, tmp_path, monkeypatch):
    async with running_app([], rag=fake_rag(tmp_path)) as (_, c):
        await seeded_kb(c, "docs-1", tmp_path, monkeypatch)
        doc_id = (await c.get("/api/kbs/docs-1/documents")).json()[0]["doc_id"]
        first = await c.get(f"/api/kbs/docs-1/documents/{doc_id}?offset=0&limit=100")
        assert first.status_code == 200
        page = first.json()
        full = "# A\n\n" + "alpha " * 400 + "\n"
        assert page["path"] == "a.md" and page["title"] == "A"
        assert page["offset"] == 0 and page["total_chars"] == len(full)
        assert page["text"] == full[:100] and page["has_more"] is True
        last = (await c.get(f"/api/kbs/docs-1/documents/{doc_id}?offset={len(full) - 10}&limit=100")).json()
        assert last["text"] == full[-10:] and last["has_more"] is False


async def test_document_routes_answer_404_for_an_unknown_kb(running_app, tmp_path):
    async with running_app([], rag=fake_rag(tmp_path)) as (_, c):
        assert (await c.get("/api/kbs/nope/documents")).status_code == 404
        assert (await c.get("/api/kbs/nope/documents/00000000-0000-0000-0000-000000000000")).status_code == 404


async def test_document_routes_answer_404_for_an_unknown_or_foreign_doc(running_app, tmp_path, monkeypatch):
    async with running_app([], rag=fake_rag(tmp_path)) as (_, c):
        await seeded_kb(c, "docs-1", tmp_path, monkeypatch)
        (tmp_path / "a.md").write_text("# B\n\nbeta body text\n", encoding="utf-8")
        await c.post("/api/kbs", json=body(name="docs-2", repo_url=f"dir:{tmp_path}"), headers=H)
        await c.post("/api/kbs/docs-2/sync", headers=H)
        await wait_synced(c, "docs-2")
        foreign = (await c.get("/api/kbs/docs-2/documents")).json()[0]["doc_id"]
        assert (await c.get(f"/api/kbs/docs-1/documents/{foreign}")).status_code == 404
        missing = "00000000-0000-0000-0000-000000000000"
        assert (await c.get(f"/api/kbs/docs-1/documents/{missing}")).status_code == 404
        assert (await c.get(f"/api/kbs/docs-1/documents/not-a-uuid")).status_code == 404


async def test_document_routes_answer_503_when_rag_is_disabled(running_app):
    from langchain_core.messages import AIMessage

    async with running_app([AIMessage(content="x")]) as (_, c):
        assert (await c.get("/api/kbs/docs-1/documents")).status_code == 503
        doc = "00000000-0000-0000-0000-000000000000"
        assert (await c.get(f"/api/kbs/docs-1/documents/{doc}")).status_code == 503


async def test_document_page_rejects_invalid_paging(running_app, tmp_path, monkeypatch):
    async with running_app([], rag=fake_rag(tmp_path)) as (_, c):
        await seeded_kb(c, "docs-1", tmp_path, monkeypatch)
        doc_id = (await c.get("/api/kbs/docs-1/documents")).json()[0]["doc_id"]
        for query in ("offset=-1", "limit=0", "limit=20001", "offset=abc"):
            r = await c.get(f"/api/kbs/docs-1/documents/{doc_id}?{query}")
            assert r.status_code == 422, query
