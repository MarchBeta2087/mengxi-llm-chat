"""恢复码 Schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RecoveryUseRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    new_passphrase: str | None = Field(default=None, min_length=8, max_length=256)


class RecoveryStatus(BaseModel):
    remaining: int


class RecoveryCodesResponse(BaseModel):
    codes: list[str]
