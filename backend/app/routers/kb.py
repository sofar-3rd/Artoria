import asyncio
import hmac
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import ValidationError

from app.config import settings
from app.rag.bootstrap import Rag
from app.rag.core.errors import KnowledgeBaseExists, RagError, UnknownKnowledgeBase
from app.rag.interfaces.validation import validate_branch, validate_name, validate_repo_url, validate_subdir
from app.schemas import KbCreate, KbDetail, KbOut

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_BODY_BYTES = 64 * 1024  # a knowledge base definition is a few hundred bytes


def get_rag(request: Request) -> Rag:
    rag = request.app.state.rag
    if rag is None:
        raise HTTPException(status_code=503, detail="knowledge base is not enabled (set RAG_ENABLED=true)")
    return rag


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    """Creating knowledge bases and starting syncs changes what the agent can read: it needs a token."""
    expected = settings.rag_admin_token
    if not expected:
        raise HTTPException(status_code=403, detail="knowledge base administration is disabled")
    if x_admin_token is None or not hmac.compare_digest(x_admin_token.encode(), expected.encode()):
        raise HTTPException(status_code=403, detail="invalid admin token")


@router.get("/kbs", response_model=list[KbOut])
async def list_kbs(rag: Rag = Depends(get_rag)):
    return await rag.catalog.list_kbs()


@router.post("/kbs", response_model=KbOut, status_code=201, dependencies=[Depends(require_admin)])
async def create_kb(request: Request, rag: Rag = Depends(get_rag)):
    # `require_admin` runs before this body is read: FastAPI parses a declared body model BEFORE dependencies
    # finish, so an unauthenticated caller would otherwise get validation errors and force JSON decoding.
    raw = await _read_limited(request)
    try:
        body = KbCreate.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=[{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()]) from exc
    try:
        name = validate_name(body.name)
        branch = validate_branch(body.branch)
        subdir = validate_subdir(body.subdir)
        repo_url = validate_repo_url(body.repo_url, local_root=settings.rag_local_root)
        kb = await rag.store.create_kb(
            name, body.description, repo_url, branch, subdir, rag.embedder.model, rag.embedder.dim
        )
    except KnowledgeBaseExists as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return KbOut(name=kb.name, description=kb.description, doc_count=0, synced_at=None, last_error=None)


async def _read_limited(request: Request) -> bytes:
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="request body too large")
    chunks, size = [], 0
    async for chunk in request.stream():  # also covers chunked uploads that declare no length
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="request body too large")
        chunks.append(chunk)
    return b"".join(chunks)


async def _info(rag: Rag, name: str):
    try:
        await rag.store.get_kb(name)
    except UnknownKnowledgeBase as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return next(i for i in await rag.catalog.list_kbs() if i.name == name)


@router.get("/kbs/{name}", response_model=KbDetail)
async def get_kb(name: str, request: Request, rag: Rag = Depends(get_rag)):
    # Read the in-memory `running` flag BEFORE the database. A sync clears the flag only after it has
    # written its final state, so `running=False` guarantees the row we read next is already final.
    # Reading them the other way round can report "not running" together with a stale "no error".
    running = name in request.app.state.sync_running
    info = await _info(rag, name)
    kb = await rag.store.get_kb(name)
    return KbDetail(**info.__dict__, last_commit=kb.last_commit, running=running)


@router.post("/kbs/{name}/sync", status_code=202, dependencies=[Depends(require_admin)])
async def sync_kb(name: str, request: Request, rag: Rag = Depends(get_rag)):
    await _info(rag, name)  # 404 for an unknown name
    state = request.app.state
    if name in state.sync_running:
        raise HTTPException(status_code=409, detail=f"a sync of '{name}' is already running")
    state.sync_running.add(name)
    task = asyncio.create_task(_run_sync(rag, state, name))
    state.sync_tasks.add(task)  # keep a reference: the event loop only holds tasks weakly
    task.add_done_callback(state.sync_tasks.discard)
    return {"status": "started"}


async def _run_sync(rag: Rag, state, name: str) -> None:
    try:
        await rag.syncer.sync(name)
    except RagError as exc:
        logger.warning("sync of %s failed: %s", name, exc)  # also recorded in the knowledge base's last_error
    except Exception:
        logger.exception("sync of %s crashed", name)
    finally:
        state.sync_running.discard(name)


async def drain_syncs(app) -> None:
    """Called when the app shuts down: let running syncs finish (or fail) before the pool closes."""
    tasks = list(getattr(app.state, "sync_tasks", ()))
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
