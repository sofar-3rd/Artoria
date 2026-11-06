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


async def wait_synced(client, name, tries=100):
    for _ in range(tries):
        info = (await client.get(f"/api/kbs/{name}")).json()
        if not info["running"]:
            return info
        await asyncio.sleep(0.05)
    raise AssertionError("sync did not finish")


async def test_create_list_sync_flow(running_app, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "rag_local_root", str(tmp_path))
    (tmp_path / "a.md").write_text("# A\n\nalpha body text is here\n", encoding="utf-8")
    async with running_app([], rag=fake_rag(tmp_path)) as (_, c):
        r = await c.post("/api/kbs", json=body(repo_url=f"dir:{tmp_path}"), headers=H)
        assert r.status_code == 201 and r.json()["name"] == "docs-1"
        assert (await c.post("/api/kbs", json=body(), headers=H)).status_code == 409
        assert (await c.post("/api/kbs/docs-1/sync", headers=H)).json() == {"status": "started"}
        info = await wait_synced(c, "docs-1")
        assert info["doc_count"] == 1 and info["last_error"] is None and info["synced_at"] and info["last_commit"]
        assert [k["name"] for k in (await c.get("/api/kbs")).json()] == ["docs-1"]


async def test_unknown_kb_is_404(running_app, tmp_path):
    async with running_app([], rag=fake_rag(tmp_path)) as (_, c):
        assert (await c.post("/api/kbs/nope/sync", headers=H)).status_code == 404
        assert (await c.get("/api/kbs/nope")).status_code == 404


async def test_mutations_are_disabled_until_a_token_is_configured(running_app, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "rag_admin_token", "")
    async with running_app([], rag=fake_rag(tmp_path)) as (_, c):
        for r in (await c.post("/api/kbs", json=body(), headers=H), await c.post("/api/kbs/x/sync", headers=H)):
            assert r.status_code == 403 and "disabled" in r.json()["detail"]
        assert (await c.get("/api/kbs")).status_code == 200  # reading stays possible


@pytest.mark.parametrize("headers", [{}, {"X-Admin-Token": "wrong"}, {"X-Admin-Token": ""}, {"X-Admin-Token": TOKEN + "x"}])
async def test_wrong_or_missing_token_is_refused(running_app, tmp_path, headers):
    async with running_app([], rag=fake_rag(tmp_path)) as (_, c):
        assert (await c.post("/api/kbs", json=body(), headers=headers)).status_code == 403
        assert (await c.post("/api/kbs/x/sync", headers=headers)).status_code == 403
        assert (await c.get("/api/kbs")).json() == []  # nothing was created


@pytest.mark.parametrize(
    "overrides",
    [
        {"repo_url": "dir:/etc"},
        {"repo_url": "/usr/share/doc"},
        {"repo_url": "--upload-pack=touch /tmp/x"},
        {"repo_url": "ext::sh -c id"},
        {"repo_url": "file:///etc"},
        {"name": "has space"},
        {"name": "../x"},
        {"branch": "--config=core.sshCommand=x"},
        {"subdir": "../../etc"},
        {"description": ""},
        {"repo_url": ""},
    ],
)
async def test_dangerous_or_malformed_definitions_are_rejected_with_422(running_app, tmp_path, overrides):
    async with running_app([], rag=fake_rag(tmp_path)) as (_, c):
        r = await c.post("/api/kbs", json=body(**overrides), headers=H)
        assert r.status_code == 422
        assert (await c.get("/api/kbs")).json() == []


async def test_local_directories_are_refused_through_the_api_by_default(running_app, tmp_path):
    async with running_app([], rag=fake_rag(tmp_path)) as (_, c):
        r = await c.post("/api/kbs", json=body(repo_url=f"dir:{tmp_path}"), headers=H)
        assert r.status_code == 422 and "not allowed" in r.json()["detail"]


async def test_a_second_sync_while_one_runs_is_a_409(running_app, tmp_path, monkeypatch):
    release = asyncio.Event()

    class SlowSource:
        async def snapshot(self):
            await release.wait()
            return await DirSource(tmp_path).snapshot()

    (tmp_path / "a.md").write_text("# A\n\nalpha body text is here\n", encoding="utf-8")
    rag = build_rag(embedder=HashEmbedder(), reranker=None, count_tokens=len, source_factory=lambda kb: SlowSource())
    async with running_app([], rag=rag) as (app, c):
        await c.post("/api/kbs", json=body(), headers=H)
        assert (await c.post("/api/kbs/docs-1/sync", headers=H)).status_code == 202
        assert (await c.get("/api/kbs/docs-1")).json()["running"] is True
        try:
            again = await asyncio.wait_for(c.post("/api/kbs/docs-1/sync", headers=H), 5)
            assert again.status_code == 409 and "already running" in again.json()["detail"]
        finally:
            release.set()  # never leave the first sync blocked, whatever the assertion says
        info = await wait_synced(c, "docs-1")
        assert info["doc_count"] == 1
        assert (await c.post("/api/kbs/docs-1/sync", headers=H)).status_code == 202  # allowed again
        await wait_synced(c, "docs-1")
        assert app.state.sync_running == set()


async def test_a_failed_sync_is_visible_and_does_not_leave_the_kb_stuck_running(running_app, tmp_path):
    class BrokenSource:
        async def snapshot(self):
            raise RuntimeError("remote exploded")

    rag = build_rag(embedder=HashEmbedder(), reranker=None, count_tokens=len, source_factory=lambda kb: BrokenSource())
    async with running_app([], rag=rag) as (app, c):
        await c.post("/api/kbs", json=body(), headers=H)
        await c.post("/api/kbs/docs-1/sync", headers=H)
        info = await wait_synced(c, "docs-1")
        assert info["running"] is False and "remote exploded" in info["last_error"]
        assert app.state.sync_running == set()


async def test_routes_answer_503_when_the_knowledge_base_is_not_enabled(running_app):
    async with running_app([AIMessageStub()]) as (_, c):
        assert (await c.get("/api/kbs")).status_code == 503
        assert (await c.post("/api/kbs", json=body(), headers=H)).status_code == 503


async def test_the_token_is_not_echoed_in_errors(running_app, tmp_path):
    async with running_app([], rag=fake_rag(tmp_path)) as (_, c):
        r = await c.post("/api/kbs", json=body(), headers={"X-Admin-Token": "guess"})
        assert TOKEN not in r.text


def AIMessageStub():
    from langchain_core.messages import AIMessage

    return AIMessage(content="x")


async def test_the_reported_state_is_never_contradictory_while_a_sync_finishes(running_app):
    """`running=False` must imply the final state is already visible (last_error / synced_at)."""

    class BrokenSource:
        async def snapshot(self):
            raise RuntimeError("remote exploded")

    rag = build_rag(embedder=HashEmbedder(), reranker=None, count_tokens=len, source_factory=lambda kb: BrokenSource())
    async with running_app([], rag=rag) as (_, c):
        for round_ in range(15):
            name = f"race-{round_}"
            await c.post("/api/kbs", json=body(name=name), headers=H)
            await c.post(f"/api/kbs/{name}/sync", headers=H)
            for _ in range(400):  # poll as fast as possible: the window is a few milliseconds wide
                info = (await c.get(f"/api/kbs/{name}")).json()
                if not info["running"]:
                    assert info["last_error"] == "remote exploded", f"round {round_}: finished without a visible error"
                    break
            else:
                raise AssertionError("sync never finished")


async def test_shutdown_waits_for_a_running_sync_before_the_pool_closes(tmp_path):
    """A sync still running when the app stops must finish (or fail) first, not write to a closed pool."""
    from httpx import ASGITransport, AsyncClient
    from langchain_core.messages import AIMessage

    from app.main import create_app
    from tests.fakes import Scripted

    finished = asyncio.Event()
    started = asyncio.Event()

    class SlowSource:
        async def snapshot(self):
            started.set()
            await asyncio.sleep(0.4)
            finished.set()
            return await DirSource(tmp_path).snapshot()

    (tmp_path / "a.md").write_text("# A\n\nalpha body text is here\n", encoding="utf-8")
    rag = build_rag(embedder=HashEmbedder(), reranker=None, count_tokens=len, source_factory=lambda kb: SlowSource())
    app = create_app(model=Scripted(script=[AIMessage(content="x")]), rag=rag)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            await c.post("/api/kbs", json=body(name="slow-kb"), headers=H)
            await c.post("/api/kbs/slow-kb/sync", headers=H)
            await asyncio.wait_for(started.wait(), 5)
            assert not finished.is_set()
    assert finished.is_set()  # leaving the lifespan blocked until the sync completed
    assert app.state.sync_running == set()
