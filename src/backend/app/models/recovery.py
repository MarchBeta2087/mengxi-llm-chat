"""恢复码与审计日志模型（见设计说明书 §10.1）。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, LargeBinary, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin
from app.db.types import bigint_pk_type, inet_type


class RecoveryCode(Base, CreatedAtMixin):
    __tablename__ = "recovery_codes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True, nullable=False)
    salt: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    kek_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base, CreatedAtMixin):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(bigint_pk_type(), primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    key_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    key_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    base_url_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fallback_to_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    client_ip: Mapped[str | None] = mapped_column(inet_type(), nullable=True)
