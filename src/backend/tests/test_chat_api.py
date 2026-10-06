"""SSE 聊天接口集成测试（fakeredis + 假上游）。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.infra.upstream import UpstreamChunk
from tests.conftest import register

SECRET = "sk-chat-secret-000011112222"


class FakeUpstreamClient:
    """按序产出若干增量，最后一帧带 usage。"""

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
def _fake_upstream(monkeypatch):
    FakeUpstreamClient.calls = []
    monkeypatch.setattr("app.services.chat.UpstreamClient", FakeUpstreamClient)


def _create_key(client: TestClient, models: list[str] | None = None) -> dict:
    resp = client.post(
        "/api/keys",
        json={
            "provider_name": "上游",
            "api_key": SECRET,
            "base_url": "https://api.openai.com/v1",
            "models": models or ["gpt-4o"],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def _chat(client: TestClient, model: str = "gpt-4o") -> str:
    with client.stream(
        "POST",
        "/api/chat/completions",
        json={"model": model, "messages": [{"role": "user", "content": "在吗"}]},
    ) as resp:
        assert resp.status_code == 200, resp.text
        return "".join(resp.iter_text())


def test_streams_deltas_usage_and_done(client: TestClient) -> None:
    register(client)
    _create_key(client)

    body = _chat(client)
    assert "event: meta" in body
    assert '"pool": "private"' in body
    assert '"fallback": false' in body
    assert 'event: delta\ndata: {"text": "你好"}' in body
    assert '"text": "，世界"' in body
    assert '"tokens_in": 5' in body
    assert '"tokens_out": 3' in body
    assert "event: done" in body

    # 上游收到的密文解密后应为原始 Key
    assert FakeUpstreamClient.calls[-1]["api_key"] == SECRET
    assert FakeUpstreamClient.calls[-1]["payload"]["stream"] is True


def test_audit_recorded(client: TestClient, db_path: Path) -> None:
    register(client)
    _create_key(client)
    _chat(client)

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT key_type, status, fallback_to_public, tokens_in, tokens_out FROM audit_logs"
        ).fetchone()
    finally:
        conn.close()
    assert row == ("private", 200, 0, 5, 3)


def test_no_key_pool_returns_error_event(client: TestClient) -> None:
    register(client)
    body = _chat(client)
    assert "event: error" in body
    assert '"code": 503' in body


def test_user_daily_quota_blocks(client: TestClient, db_path: Path) -> None:
    register(client)
    _create_key(client)
    conn = sqlite3.connect(db_path)
    try:
        # 配额 5，但单次请求消耗 8 tokens（响应后累计），下次请求应被拒
        conn.execute("UPDATE users SET daily_quota_tokens=5")
        conn.commit()
    finally:
        conn.close()

    first = _chat(client)
    assert '"tokens_in": 5' in first

    second = _chat(client)
    assert "event: error" in second
    assert '"code": 42901' in second
    assert "今日配额已用完" in second


def test_private_fallback_to_public(client: TestClient, db_path: Path) -> None:
    # 管理员创建公有 Key
    register(client, "admin")
    from tests.conftest import promote_to_admin

    promote_to_admin(db_path, "admin")
    client.post(
        "/api/keys",
        json={
            "provider_name": "公共池",
            "api_key": "sk-public-0000zzzz",
            "base_url": "https://api.deepseek.com/v1",
            "models": ["gpt-4o"],
            "is_public": True,
        },
    )
    client.post("/api/auth/logout")

    # 普通用户私有 Key 限制 rpm=1 并立刻用满
    register(client, "bob")
    key = _create_key(client, models=["gpt-4o"])

    # 通过接口把私有 Key 限流设为 rpm=1
    client.patch(f"/api/keys/{key['id']}", json={"rate_limits": {"rpm": 1}})
    first = _chat(client)  # 使用私有 Key，占用 rpm=1
    assert '"pool": "private"' in first

    second = _chat(client)  # 私有已满，应回退公有
    assert '"fallback": true' in second
    assert '"pool": "public"' in second
