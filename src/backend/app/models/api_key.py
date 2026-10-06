"""API Key 模型（见设计说明书 §10.1）。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.db.types import json_type
from app.models.enums import KeyPool, KeyStatus


class ApiKey(Base, TimestampMixin):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    models_json: Mapped[list] = mapped_column(json_type(), default=list, nullable=False)
    encrypted_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    rate_limits_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    weight: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=KeyStatus.ACTIVE.value, nullable=False)
    priority_pool: Mapped[str] = mapped_column(String(16), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    usage_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)

    @property
    def is_public(self) -> bool:
        return self.priority_pool == KeyPool.PUBLIC.value

    @property
    def is_active(self) -> bool:
        return self.status == KeyStatus.ACTIVE.value
