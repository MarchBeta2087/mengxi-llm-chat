"""应用配置：环境变量前缀 MENGXI_（见设计说明书 §13.2）。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MENGXI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- 基础 ---
    app_name: str = "梦溪畅谈"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    data_dir: Path = Path("./data")

    # --- 主密钥 KEK（§3.3）---
    kek_profile: Literal["A", "B", "C"] = "A"
    master_key_b64: str | None = None
    argon2_time_cost: int = Field(default=3, ge=1)
    argon2_memory_cost: int = Field(default=65536, ge=8192)
    argon2_parallelism: int = Field(default=4, ge=1)
    argon2_hash_len: int = Field(default=32, ge=16, le=64)
    kek_lock_threshold: int = Field(default=5, ge=1)
    kek_lock_seconds: int = Field(default=900, ge=0)

    # --- SSRF（§4.4）---
    allow_http_upstream: bool = False
    domain_whitelist: str = ""
    max_redirects: int = Field(default=5, ge=0, le=10)

    # --- 存储 ---
    database_url: str = "postgresql+asyncpg://mengxi:mengxi@localhost:5432/mengxi"
    redis_url: str = "redis://localhost:6379/0"
    auto_create_tables: bool = False  # 仅开发/测试；生产用 Alembic
    plugins_dir: Path | None = None  # 插件包目录，默认 data_dir/plugins

    # --- 会话 ---
    session_secret: str = "dev-insecure-change-me"
    session_cookie: str = "mengxi_session"
    session_max_age: int = 60 * 60 * 24 * 7  # 7 天

    # --- 策略 ---
    allow_anonymous: bool = False
    fallback_to_public: bool = True
    audit_retention_days: int = Field(default=90, ge=1)

    # --- 三层兜底限流（JSON 字符串，空 = 关闭）---
    # 示例：MENGXI_USER_RATE_LIMITS='{"rpm": 120, "rpd": 2000}'
    user_rate_limits: str = ""
    ip_rate_limits: str = ""

    # --- 派生路径与集合 ---
    @property
    def keys_dir(self) -> Path:
        return self.data_dir / "keys"

    @property
    def plugins_path(self) -> Path:
        return self.plugins_dir or (self.data_dir / "plugins")

    @property
    def salt_file(self) -> Path:
        return self.keys_dir / "kek.salt"

    @property
    def verifier_file(self) -> Path:
        return self.keys_dir / "kek.verify"

    @property
    def domain_whitelist_set(self) -> tuple[str, ...]:
        raw = (self.domain_whitelist or "").replace(";", ",")
        return tuple(d.strip().lower() for d in raw.split(",") if d.strip())


@lru_cache
def get_settings() -> Settings:
    """进程内单例配置。"""
    return Settings()
