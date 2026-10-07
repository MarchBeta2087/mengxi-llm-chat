"""API Key 相关 Schema。"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import KeyStatus


class RateLimits(BaseModel):
    """六维限流，0 表示不限。"""

    rpm: int = Field(default=0, ge=0)
    rph: int = Field(default=0, ge=0)
    rpd: int = Field(default=0, ge=0)
    tpm: int = Field(default=0, ge=0)
    tph: int = Field(default=0, ge=0)
    tpd: int = Field(default=0, ge=0)


class KeyCreate(BaseModel):
    provider_name: str = Field(min_length=1, max_length=64)
    api_key: str = Field(min_length=1, max_length=512)
    base_url: str = Field(min_length=1, max_length=512)
    models: list[str] = Field(default_factory=list)
    rate_limits: RateLimits = Field(default_factory=RateLimits)
    weight: int = Field(default=1, ge=1, le=1000)
    is_public: bool = False  # 仅管理员生效


class KeyUpdate(BaseModel):
    provider_name: str | None = Field(default=None, min_length=1, max_length=64)
    api_key: str | None = Field(default=None, min_length=1, max_length=512)
    base_url: str | None = Field(default=None, min_length=1, max_length=512)
    models: list[str] | None = None
    rate_limits: RateLimits | None = None
    weight: int | None = Field(default=None, ge=1, le=1000)
    status: KeyStatus | None = None


class KeyRead(BaseModel):
    """对外表示：绝不包含 Key 明文。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_name: str
    base_url: str
    models: list[str]
    masked_key: str
    rate_limits: dict
    weight: int
    status: str
    pool: str
    created_at: datetime


class KeyTestResult(BaseModel):
    ok: bool
    status_code: int
    latency_ms: int
    error: str | None = None


class KeyUsage(BaseModel):
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0


class AvailableKeyRead(BaseModel):
    """聊天可用 Key（脱敏 + 用量），供模型选择弹窗使用。"""

    id: uuid.UUID
    provider_name: str
    masked_key: str
    models: list[str]
    pool: str
    usage_scope: str  # global（公有池） / personal（私有）
    last_used_at: datetime | None = None
    usage: KeyUsage
