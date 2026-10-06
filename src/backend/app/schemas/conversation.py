"""会话与消息 Schema。"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    title: str = Field(default="新会话", max_length=200)
    model: str | None = Field(default=None, max_length=128)
    encrypted: bool = True


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    archived: bool | None = None


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    model: str | None
    encrypted: bool
    archived: bool
    created_at: datetime


class MessageRead(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    tokens_in: int
    tokens_out: int
    created_at: datetime


class SearchResult(BaseModel):
    conversation_id: str
    title: str
    kind: str
    message_id: str | None = None
    snippet: str | None = None
