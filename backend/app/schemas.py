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
