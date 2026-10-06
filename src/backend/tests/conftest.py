"""测试夹具：SQLite 文件库 + 档 B 主密钥 + TestClient。"""

from __future__ import annotations

import base64
import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def master_key_b64() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def settings(tmp_path: Path, db_path: Path, master_key_b64: str) -> Settings:
    return Settings(
        environment="development",
        kek_profile="B",
        master_key_b64=master_key_b64,
        database_url=f"sqlite+aiosqlite:///{db_path.as_posix()}",
        auto_create_tables=True,
        data_dir=tmp_path / "data",
        session_secret="test-secret-key",
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def register(client: TestClient, username: str = "alice", password: str = "password123") -> dict:
    resp = client.post("/api/auth/register", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def promote_to_admin(db_path: Path, username: str) -> None:
    """测试辅助：直接改库把用户提升为管理员（避免跨事件循环操作 async 引擎）。"""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("UPDATE users SET role='admin' WHERE username=?", (username,))
        conn.commit()
    finally:
        conn.close()
