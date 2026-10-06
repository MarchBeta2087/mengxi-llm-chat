"""初始表结构：用户、用户组、API Key、恢复码、审计日志。

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-06

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.types import bigint_pk_type, inet_type, json_type

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_groups",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("daily_quota_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("settings_json", json_type(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="user"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("conversation_key_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("daily_quota_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("group_id", sa.Uuid(), sa.ForeignKey("user_groups.id"), nullable=True),
        sa.Column("settings_json", json_type(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "api_keys",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("provider_name", sa.String(64), nullable=False),
        sa.Column("base_url", sa.String(512), nullable=False),
        sa.Column("models_json", json_type(), nullable=False),
        sa.Column("encrypted_key", sa.LargeBinary(), nullable=False),
        sa.Column("key_fingerprint", sa.String(64), nullable=False),
        sa.Column("rate_limits_json", json_type(), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("priority_pool", sa.String(16), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("usage_json", json_type(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
    op.create_index("ix_api_keys_pool", "api_keys", ["priority_pool", "status"])

    op.create_table(
        "recovery_codes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("code_hash", sa.LargeBinary(), nullable=False, unique=True),
        sa.Column("salt", sa.LargeBinary(), nullable=False),
        sa.Column("kek_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", bigint_pk_type(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("key_id", sa.Uuid(), nullable=True),
        sa.Column("key_type", sa.String(16), nullable=True),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("base_url_host", sa.String(255), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fallback_to_public", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("client_ip", inet_type(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("recovery_codes")
    op.drop_table("api_keys")
    op.drop_table("users")
    op.drop_table("user_groups")
