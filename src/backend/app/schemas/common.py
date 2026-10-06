"""通用 Schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PassphraseRequest(BaseModel):
    passphrase: str = Field(min_length=8, max_length=256)
