"""聊天相关 Schema。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChatMessageIn(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=100_000)


class ChatCompletionRequest(BaseModel):
    model: str = Field(min_length=1, max_length=128)
    messages: list[ChatMessageIn] = Field(min_length=1, max_length=200)
