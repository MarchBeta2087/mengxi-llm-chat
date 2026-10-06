"""测试夹具：SQLite 文件库 + 档 B 主密钥 + TestClient。"""

from __future__ import annotations

import base64
import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fakeredis.aioredis import FakeRedis
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.infra.redis_store import RedisStore
from app.infra.upstream import UpstreamChunk
from app.main import create_app


class FakeUpstreamClient:
    """假上游：按序产出增量，最后一帧带 usage。供全部测试使用，避免真实网络。"""

    calls: list[dict] = []

    def __init__(self, policy, *, timeout: float = 120.0) -> None:
        self.policy = policy

    async def stream_chat(self, *, base_url: str, api_key: str, payload: dict):
        FakeUpstreamClient.calls.append(
            {"base_url": base_url, "api_key": api_key, "payload": payload}
        )
        yield UpstreamChunk(text="你好")
        yield UpstreamChunk(text="，世界")
        yield UpstreamChunk(usage={"prompt_tokens": 5, "completion_tokens": 3})


@pytest.fixture(autouse=True)
def _fake_upstream(monkeypatch) -> None:
    FakeUpstreamClient.calls = []
    monkeypatch.setattr("app.services.chat.UpstreamClient", FakeUpstreamClient)


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
    fake_redis = FakeRedis(decode_responses=True)
    store = RedisStore("redis://fake", client=fake_redis)
    app = create_app(settings, redis_store=store)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client_factory(settings: Settings):
    """按需以覆盖后的配置创建多个 TestClient（已进入 lifespan）。"""
    opened: list[TestClient] = []

    def _make(**overrides) -> TestClient:
        cfg = settings.model_copy(update=overrides)
        fake_redis = FakeRedis(decode_responses=True)
        store = RedisStore("redis://fake", client=fake_redis)
        app = create_app(cfg, redis_store=store)
        test_client = TestClient(app)
        test_client.__enter__()
        opened.append(test_client)
        return test_client

    yield _make
    for test_client in opened:
        test_client.__exit__(None, None, None)


def register(client: TestClient, username: str = "alice", password: str = "password123") -> dict:
    resp = client.post("/api/auth/register", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def login(client: TestClient, username: str, password: str = "password123") -> dict:
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def create_key(
    client: TestClient,
    *,
    api_key: str = "sk-test-key-0000",
    base_url: str = "https://api.openai.com/v1",
    models: list[str] | None = None,
    **extra,
) -> dict:
    payload = {
        "provider_name": "测试通道",
        "api_key": api_key,
        "base_url": base_url,
        "models": models or ["gpt-4o"],
        **extra,
    }
    resp = client.post("/api/keys", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def chat(client: TestClient, model: str = "gpt-4o") -> str:
    with client.stream(
        "POST",
        "/api/chat/completions",
        json={"model": model, "messages": [{"role": "user", "content": "hi"}]},
    ) as resp:
        assert resp.status_code == 200, resp.text
        return "".join(resp.iter_text())


def promote_to_admin(db_path: Path, username: str) -> None:
    """测试辅助：直接改库把用户提升为管理员（避免跨事件循环操作 async 引擎）。"""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("UPDATE users SET role='admin' WHERE username=?", (username,))
        conn.commit()
    finally:
        conn.close()
