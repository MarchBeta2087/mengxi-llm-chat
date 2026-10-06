"""领域枚举（数据库以字符串存储，便于迁移）。"""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


class UserStatus(StrEnum):
    ACTIVE = "active"
    BANNED = "banned"


class KeyStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    CIRCUIT_OPEN = "circuit_open"


class KeyPool(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"
