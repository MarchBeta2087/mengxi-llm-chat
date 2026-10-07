"""密钥接口集成测试：加密落库、脱敏、SSRF、鉴权、连通性。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.services.keys import ProbeResult
from tests.conftest import promote_to_admin, register

SECRET = "sk-supersecret-abcdef1234567890"


def _create_private(client: TestClient, **overrides) -> dict:
    payload = {
        "provider_name": "官方主通道",
        "api_key": SECRET,
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o", "gpt-4o-mini"],
        "rate_limits": {"rpm": 60, "rpd": 10000},
        "weight": 2,
    }
    payload.update(overrides)
    resp = client.post("/api/keys", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def test_create_and_list_masked(client: TestClient) -> None:
    register(client)
    created = _create_private(client)
    assert created["masked_key"] == "sk-...7890"
    assert created["pool"] == "private"
    assert created["models"] == ["gpt-4o", "gpt-4o-mini"]

    listed = client.get("/api/keys").json()["data"]
    assert len(listed) == 1
    # 响应中绝不出现明文
    assert SECRET not in client.get("/api/keys").text


def test_plaintext_never_stored(client: TestClient, db_path: Path) -> None:
    register(client)
    _create_private(client)

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT encrypted_key, key_fingerprint FROM api_keys").fetchall()
    finally:
        conn.close()

    assert len(rows) == 1
    blob, fingerprint = rows[0]
    assert SECRET.encode() not in blob  # 密文中不含明文
    assert fingerprint == "sk-...7890"
    assert SECRET not in fingerprint


def test_ssrf_blocks_metadata_endpoint(client: TestClient) -> None:
    register(client)
    resp = client.post(
        "/api/keys",
        json={
            "provider_name": "evil",
            "api_key": SECRET,
            "base_url": "https://169.254.169.254/latest",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == 40010


def test_ssrf_blocks_http_by_default(client: TestClient) -> None:
    register(client)
    resp = client.post(
        "/api/keys",
        json={"provider_name": "x", "api_key": SECRET, "base_url": "http://example.com/v1"},
    )
    assert resp.status_code == 400


def test_update_rotate_secret(client: TestClient) -> None:
    register(client)
    created = _create_private(client)
    key_id = created["id"]

    resp = client.patch(
        f"/api/keys/{key_id}",
        json={"api_key": "sk-rotated-0000zzzz", "weight": 5, "status": "disabled"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["masked_key"] == "sk-...zzzz"
    assert data["weight"] == 5
    assert data["status"] == "disabled"


def test_delete(client: TestClient) -> None:
    register(client)
    created = _create_private(client)
    assert client.delete(f"/api/keys/{created['id']}").status_code == 200
    assert client.get("/api/keys").json()["data"] == []
    assert client.delete(f"/api/keys/{created['id']}").status_code == 404


def test_owner_isolation(client: TestClient) -> None:
    register(client, "alice")
    created = _create_private(client)
    key_id = created["id"]
    client.post("/api/auth/logout")

    register(client, "bob")
    # bob 不能看到/操作 alice 的 Key
    assert client.get("/api/keys").json()["data"] == []
    assert client.patch(f"/api/keys/{key_id}", json={"weight": 9}).status_code == 403
    assert client.delete(f"/api/keys/{key_id}").status_code == 403


def test_connectivity_test_records_audit(client: TestClient, db_path: Path, monkeypatch) -> None:
    class _FakeProbe:
        def __init__(self, policy) -> None:
            self.policy = policy

        async def __call__(self, base_url: str, api_key: str, *, timeout: float = 10.0):
            assert api_key == SECRET  # 服务端确实解密出了明文用于探测
            return ProbeResult(ok=True, status_code=200, latency_ms=7, error=None)

    monkeypatch.setattr("app.services.keys.HttpUpstreamProbe", _FakeProbe)

    register(client)
    created = _create_private(client)
    resp = client.post(f"/api/keys/{created['id']}/test")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["ok"] is True
    assert resp.json()["data"]["latency_ms"] == 7

    conn = sqlite3.connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
        host = conn.execute("SELECT base_url_host FROM audit_logs").fetchone()[0]
    finally:
        conn.close()
    assert count == 1
    assert host == "api.openai.com"


def test_models_endpoint(client: TestClient) -> None:
    register(client)
    _create_private(client, models=["gpt-4o", "claude-*"])
    models = client.get("/api/keys/models").json()["data"]
    assert models == ["gpt-4o", "claude-*"]


def test_models_include_public_pool(client: TestClient, db_path: Path) -> None:
    """普通用户的模型列表应包含私有 + 公有池（回归）。"""
    register(client, "admin")
    promote_to_admin(db_path, "admin")
    client.post(
        "/api/keys",
        json={
            "provider_name": "公共池",
            "api_key": "sk-public-deepseek",
            "base_url": "https://api.deepseek.com/v1",
            "models": ["deepseek-chat"],
            "is_public": True,
        },
    )
    client.post("/api/auth/logout")

    register(client, "bob")
    _create_private(client, models=["gpt-4o"])
    models = client.get("/api/keys/models").json()["data"]
    assert {"gpt-4o", "deepseek-chat"} <= set(models)


def test_models_exclude_disabled(client: TestClient) -> None:
    register(client)
    created = _create_private(client)
    client.patch(f"/api/keys/{created['id']}", json={"status": "disabled"})
    assert client.get("/api/keys/models").json()["data"] == []


def test_admin_public_key_and_isolation(client: TestClient, db_path: Path) -> None:
    register(client, "admin")
    promote_to_admin(db_path, "admin")

    resp = client.post(
        "/api/keys",
        json={
            "provider_name": "公共池",
            "api_key": SECRET,
            "base_url": "https://api.deepseek.com/v1",
            "is_public": True,
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["pool"] == "public"

    public = client.get("/api/keys", params={"pool": "public"}).json()["data"]
    assert len(public) == 1
