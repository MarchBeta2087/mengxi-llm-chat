"""插件相关 Schema：Manifest 规范与对外表示。"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RuntimeLimits(BaseModel):
    timeout_ms: int = Field(default=10_000, ge=100, le=60_000)
    memory_mb: int = Field(default=128, ge=16, le=1024)
    cpu_seconds: int = Field(default=5, ge=1, le=60)


class PluginManifest(BaseModel):
    """插件清单（见设计说明书 §6.1）。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    version: str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    description: str = Field(default="", max_length=500)
    type: str = Field(default="optional", pattern=r"^(global|optional)$")
    entry: str = Field(default="main.py", max_length=128)
    permissions: list[str] = Field(default_factory=list, max_length=32)
    default_state: str = Field(default="disabled", pattern=r"^(enabled|disabled)$")
    runtime: RuntimeLimits = Field(default_factory=RuntimeLimits)

    @field_validator("entry")
    @classmethod
    def _entry_is_basename(cls, value: str) -> str:
        if "/" in value or "\\" in value or value in ("..", "."):
            raise ValueError("entry 必须是插件目录内的文件名")
        return value

    @field_validator("permissions")
    @classmethod
    def _permissions_well_formed(cls, value: list[str]) -> list[str]:
        from app.domain.plugins import parse_permission

        for item in value:
            parse_permission(item)  # 非法即抛错
        return value


class PluginInstall(BaseModel):
    manifest: PluginManifest
    code: str = Field(min_length=1, max_length=200_000)


class BuiltinInstall(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class PluginUpdate(BaseModel):
    type: str | None = Field(default=None, pattern=r"^(global|optional)$")
    default_state: str | None = Field(default=None, pattern=r"^(enabled|disabled)$")
    status: str | None = Field(default=None, pattern=r"^(active|disabled)$")


class PluginToggle(BaseModel):
    enabled: bool


class GroupPluginSet(BaseModel):
    state: str = Field(pattern=r"^(enabled|disabled)$")


class PluginInvoke(BaseModel):
    input: dict = Field(default_factory=dict)
    config: dict = Field(default_factory=dict)


class PluginRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    version: str
    description: str
    type: str
    default_state: str
    status: str
    permissions: list[str]
    runtime: dict
    enabled: bool
    state_source: str
