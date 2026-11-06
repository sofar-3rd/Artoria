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
