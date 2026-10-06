"""公共列类型：生产 PostgreSQL，测试用 SQLite 时通过 variant 回退。"""

from __future__ import annotations

from sqlalchemy import JSON, BigInteger, Integer, String
from sqlalchemy.dialects.postgresql import INET, JSONB


def json_type():
    """PostgreSQL 用 JSONB；其他方言（测试 SQLite）回退 JSON。"""
    return JSONB().with_variant(JSON(), "sqlite")


def inet_type():
    return INET().with_variant(String(45), "sqlite")


def bigint_pk_type():
    """自增大整数主键；SQLite 需回退为 INTEGER 才能自增。"""
    return BigInteger().with_variant(Integer(), "sqlite")
