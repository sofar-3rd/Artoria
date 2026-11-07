import base64
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Thread, Turn, TurnToolCall
from app.schemas import TurnDetail, TurnOut, TurnPage

router = APIRouter()

Status = Literal["ok", "error", "cancelled"]


def _encode(started_at: datetime, turn_id: uuid.UUID) -> str:
    raw = f"{started_at.isoformat()}|{turn_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        started, turn_id = raw.split("|", 1)
        return datetime.fromisoformat(started), uuid.UUID(turn_id)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=422, detail="invalid cursor") from exc


def _out(turn: Turn, title: str | None) -> dict:
    data = {c.name: getattr(turn, c.name) for c in Turn.__table__.columns}
    data["thread_title"] = title
    return data


@router.get("/traces", response_model=TurnPage)
async def list_turns(
    status: Status | None = None,
    thread_id: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int = Query(30, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    query = (
        select(Turn, Thread.title)
        .join(Thread, Thread.id == Turn.thread_id)
        .order_by(Turn.started_at.desc(), Turn.id.desc())
        .limit(limit + 1)
    )
    if status is not None:
        query = query.where(Turn.status == status)
    if thread_id is not None:
        query = query.where(Turn.thread_id == thread_id)
    if cursor is not None:
        started_at, turn_id = _decode(cursor)
        query = query.where(
            or_(
                Turn.started_at < started_at,
                and_(Turn.started_at == started_at, Turn.id < turn_id),
            )
        )
    rows = (await session.execute(query)).all()
    page = rows[:limit]
    more = len(rows) > limit
    return TurnPage(
        items=[_out(turn, title) for turn, title in page],
        next_cursor=_encode(page[-1][0].started_at, page[-1][0].id) if more else None,
    )


@router.get("/traces/{turn_id}", response_model=TurnDetail)
async def get_turn(turn_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    row = (
        await session.execute(
            select(Turn, Thread.title)
            .join(Thread, Thread.id == Turn.thread_id)
            .where(Turn.id == turn_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="turn not found")
    tools = (
        await session.execute(
            select(TurnToolCall)
            .where(TurnToolCall.turn_id == turn_id)
            .order_by(TurnToolCall.seq)
        )
    ).scalars().all()
    return TurnDetail(**_out(row[0], row[1]), tools=tools)
