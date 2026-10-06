"""插件系统：plugins / user_plugins / group_plugins。

Revision ID: 0002_plugins
Revises: 0001_initial
Create Date: 2026-10-06

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.types import json_type

revision: str = "0002_plugins"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plugins",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column("type", sa.String(16), nullable=False, server_default="optional"),
        sa.Column("default_state", sa.String(16), nullable=False, server_default="disabled"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("manifest_json", json_type(), nullable=False),
        sa.Column("permissions_json", json_type(), nullable=False),
        sa.Column("runtime_json", json_type(), nullable=False),
        sa.Column("package_dir", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_plugins_name", "plugins", ["name"], unique=True)

    op.create_table(
        "user_plugins",
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "plugin_id",
            sa.Uuid(),
            sa.ForeignKey("plugins.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
    )

    op.create_table(
        "group_plugins",
        sa.Column(
            "group_id",
            sa.Uuid(),
            sa.ForeignKey("user_groups.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "plugin_id",
            sa.Uuid(),
            sa.ForeignKey("plugins.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("state", sa.String(16), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("group_plugins")
    op.drop_table("user_plugins")
    op.drop_table("plugins")
