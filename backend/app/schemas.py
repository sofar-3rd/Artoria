import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.config import settings


class ThreadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ChatRequest(BaseModel):
    message: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=settings.max_message_chars
        ),
    ]


class KbCreate(BaseModel):
    name: str
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    repo_url: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    branch: str = "main"
    subdir: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] = ""


class KbOut(BaseModel):
    name: str
    description: str
    doc_count: int
    synced_at: datetime | None
    last_error: str | None


class KbDetail(KbOut):
    last_commit: str | None
    running: bool


class ToolCallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tool_call_id: str | None
    name: str
    args: dict | None
    status: str
    seq: int
    started_offset_ms: int
    duration_ms: int | None
    result_chars: int | None
    error: str | None


class TurnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    thread_id: uuid.UUID
    thread_title: str | None
    status: str
    started_at: datetime
    duration_ms: int
    ttft_ms: int | None
    first_content_ms: int | None
    llm_calls: int
    tool_calls_count: int
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    model: str | None
    error: str | None


class TurnDetail(TurnOut):
    tools: list[ToolCallOut]


class TurnPage(BaseModel):
    items: list[TurnOut]
    next_cursor: str | None
