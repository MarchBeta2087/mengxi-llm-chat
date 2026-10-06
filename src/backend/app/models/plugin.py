"""插件 ORM 模型（见设计说明书 §10.1）。"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.db.types import json_type
from app.domain.plugins import PluginState, PluginStatus, PluginType


class Plugin(Base, TimestampMixin):
    __tablename__ = "plugins"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    type: Mapped[str] = mapped_column(String(16), default=PluginType.OPTIONAL.value, nullable=False)
    default_state: Mapped[str] = mapped_column(
        String(16), default=PluginState.DISABLED.value, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), default=PluginStatus.ACTIVE.value, nullable=False
    )
    manifest_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    permissions_json: Mapped[list] = mapped_column(json_type(), default=list, nullable=False)
    runtime_json: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    package_dir: Mapped[str] = mapped_column(Text, nullable=False)

    @property
    def is_global(self) -> bool:
        return self.type == PluginType.GLOBAL.value

    @property
    def is_active(self) -> bool:
        return self.status == PluginStatus.ACTIVE.value


class UserPlugin(Base):
    __tablename__ = "user_plugins"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    plugin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plugins.id", ondelete="CASCADE"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)


class GroupPlugin(Base):
    __tablename__ = "group_plugins"

    group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_groups.id", ondelete="CASCADE"), primary_key=True
    )
    plugin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plugins.id", ondelete="CASCADE"), primary_key=True
    )
    state: Mapped[str] = mapped_column(String(16), nullable=False)
