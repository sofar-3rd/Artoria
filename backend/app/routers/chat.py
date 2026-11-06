import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat_stream import ChatRun
from app.config import settings
from app.db import get_session
from app.models import DEFAULT_TITLE
from app.routers.threads import get_thread_or_404
from app.run_response import RunResponse
from app.schemas import ChatRequest

router = APIRouter()

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@router.post("/threads/{thread_id}/chat")
async def chat(
    thread_id: uuid.UUID,
    body: ChatRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    thread = await get_thread_or_404(session, thread_id)
    if thread.title == DEFAULT_TITLE:
        thread.title = " ".join(body.message.split())[: settings.title_max_chars]
    thread.updated_at = datetime.now(timezone.utc)
    await session.commit()

    run = ChatRun(
        request.app.state.agent, str(thread_id), body.message, settings.recursion_limit
    )
    return RunResponse(run, headers=SSE_HEADERS)
