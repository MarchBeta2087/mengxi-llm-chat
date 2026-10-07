"""删除 messages.blind_index 遗留列。

消息关键词指纹统一写入 ``message_keywords`` 表，``messages.blind_index``
自引入以来从未写入，予以移除（见审查 P2-6）。

Revision ID: 0004_drop_blind_index
Revises: 0003_conversations
Create Date: 2026-10-07

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.types import json_type

revision: str = "0004_drop_blind_index"
down_revision: str | None = "0003_conversations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("messages") as batch:
        batch.drop_column("blind_index")


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch:
        batch.add_column(sa.Column("blind_index", json_type(), nullable=True))
