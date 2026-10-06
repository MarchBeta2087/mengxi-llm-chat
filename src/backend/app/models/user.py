"""用户与用户组模型（见设计说明书 §10.1）。"""

from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin
from app.db.types import json_type
from app.models.enums import UserRole, UserStatus


class UserGroup(Base, CreatedAtMixin):
    __tablename__ = "user_groups"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    daily_quota_tokens: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    settings_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)


class User(Base, CreatedAtMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default=UserRole.USER.value, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=UserStatus.ACTIVE.value, nullable=False)

    # DEK_conv 密文（由 KEK 包裹），M4 对话加密使用
    conversation_key_encrypted: Mapped[bytes | None] = mapped_column(nullable=True)

    daily_quota_tokens: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    group_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user_groups.id"), nullable=True)
    settings_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN.value

    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE.value
