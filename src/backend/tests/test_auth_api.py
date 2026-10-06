"""认证接口集成测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import register


def test_register_login_me_logout(client: TestClient) -> None:
    data = register(client, "alice")
    assert data["username"] == "alice"
    assert data["role"] == "user"

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["data"]["username"] == "alice"

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200

    assert client.get("/api/auth/me").status_code == 401


def test_duplicate_username_rejected(client: TestClient) -> None:
    register(client, "bob")
    resp = client.post("/api/auth/register", json={"username": "bob", "password": "password123"})
    assert resp.status_code == 400
    assert resp.json()["code"] == 400


def test_wrong_password_rejected(client: TestClient) -> None:
    register(client, "carol")
    client.post("/api/auth/logout")
    resp = client.post("/api/auth/login", json={"username": "carol", "password": "wrong-password"})
    assert resp.status_code == 401
    assert resp.json()["code"] == 401


def test_me_requires_auth(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401
