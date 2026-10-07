"""管理后台相关 Schema。"""

from __future__ import annotations

import uuid
from datetime import datetime
from ipaddress import IPv4Address, IPv6Address

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import UserRole, UserStatus


class UserAdminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    role: str
    status: str
    daily_quota_tokens: int
    group_id: uuid.UUID | None


class UserAdminUpdate(BaseModel):
    daily_quota_tokens: int | None = Field(default=None, ge=0)
    status: UserStatus | None = None
    role: UserRole | None = None
    group_id: uuid.UUID | None = None


class GroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    daily_quota_tokens: int


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    daily_quota_tokens: int = Field(default=0, ge=0)


class GroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    daily_quota_tokens: int | None = Field(default=None, ge=0)


class AuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: uuid.UUID | None
    key_id: uuid.UUID | None
    key_type: str | None
    model: str | None
    base_url_host: str | None
    tokens_in: int
    tokens_out: int
    latency_ms: int
    status: int
    fallback_to_public: bool
    client_ip: str | None
    created_at: datetime

    @field_validator("client_ip", mode="before")
    @classmethod
    def _coerce_client_ip(cls, value: object) -> object:
        # PostgreSQL INET 经 asyncpg 可能返回 ipaddress 对象，统一转为字符串
        if isinstance(value, (IPv4Address, IPv6Address)):
            return str(value)
        return value
