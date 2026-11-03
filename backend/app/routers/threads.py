import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.history import to_view
from app.models import Thread
from app.schemas import ThreadOut

router = APIRouter()


async def get_thread_or_404(session: AsyncSession, thread_id: uuid.UUID) -> Thread:
    thread = await session.get(Thread, thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="thread not found")
    return thread


@router.post("/threads", response_model=ThreadOut, status_code=201)
async def create_thread(session: AsyncSession = Depends(get_session)):
    thread = Thread()
    session.add(thread)
    await session.commit()
    await session.refresh(thread)
    return thread


@router.get("/threads", response_model=list[ThreadOut])
async def list_threads(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Thread).order_by(Thread.updated_at.desc()))
    return result.scalars().all()


@router.delete("/threads/{thread_id}", status_code=204)
async def delete_thread(
    thread_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    thread = await get_thread_or_404(session, thread_id)
    # Checkpointer data first: an orphan row is harmless, orphan checkpoints leak.
    await request.app.state.checkpointer.adelete_thread(str(thread_id))
    await session.delete(thread)
    await session.commit()
    return Response(status_code=204)


@router.get("/threads/{thread_id}/messages")
async def get_messages(
    thread_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    await get_thread_or_404(session, thread_id)
    config = {"configurable": {"thread_id": str(thread_id)}}
    state = await request.app.state.agent.aget_state(config)
    return to_view(state.values.get("messages", []))
