"""管理后台接口测试：用户、用户组、配额。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import login, promote_to_admin, register


def _seed_admin(client: TestClient, db_path: Path, name: str = "admin") -> None:
    register(client, name)
    promote_to_admin(db_path, name)


def test_non_admin_forbidden(client: TestClient) -> None:
    register(client, "bob")
    assert client.get("/api/admin/users").status_code == 403
    assert client.get("/api/admin/groups").status_code == 403


def test_kek_endpoints_require_admin(client: TestClient) -> None:
    """P0-1：主密钥端点必须鉴权。"""
    passphrase = {"passphrase": "x" * 12}
    # 未登录
    assert client.get("/api/admin/kek").status_code == 401
    assert client.post("/api/admin/kek/lock").status_code == 401
    assert client.post("/api/admin/kek/unlock", json=passphrase).status_code == 401
    assert client.post("/api/admin/kek/initialize", json=passphrase).status_code == 401

    # 普通用户
    register(client, "bob")
    assert client.get("/api/admin/kek").status_code == 403
    assert client.post("/api/admin/kek/lock").status_code == 403
    assert client.post("/api/admin/kek/unlock", json=passphrase).status_code == 403
    assert client.post("/api/admin/kek/initialize", json=passphrase).status_code == 403


def test_list_users_and_set_quota(client: TestClient, db_path: Path) -> None:
    _seed_admin(client, db_path)
    register(client, "bob")
    login(client, "admin")

    users = client.get("/api/admin/users").json()["data"]
    assert {u["username"] for u in users} == {"admin", "bob"}

    bob = next(u for u in users if u["username"] == "bob")
    resp = client.patch(
        f"/api/admin/users/{bob['id']}",
        json={"daily_quota_tokens": 1234, "status": "banned"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["daily_quota_tokens"] == 1234
    assert resp.json()["data"]["status"] == "banned"

    # 被封禁用户无法登录
    client.post("/api/auth/logout")
    banned = client.post("/api/auth/login", json={"username": "bob", "password": "password123"})
    assert banned.status_code == 403


def test_group_crud_and_assign(client: TestClient, db_path: Path) -> None:
    _seed_admin(client, db_path)

    created = client.post("/api/admin/groups", json={"name": "研发组", "daily_quota_tokens": 500})
    assert created.status_code == 201, created.text
    group_id = created.json()["data"]["id"]

    duplicate = client.post("/api/admin/groups", json={"name": "研发组"})
    assert duplicate.status_code == 400

    updated = client.patch(f"/api/admin/groups/{group_id}", json={"daily_quota_tokens": 900})
    assert updated.json()["data"]["daily_quota_tokens"] == 900

    register(client, "bob")
    login(client, "admin")
    bob = next(u for u in client.get("/api/admin/users").json()["data"] if u["username"] == "bob")
    assigned = client.patch(f"/api/admin/users/{bob['id']}", json={"group_id": group_id})
    assert assigned.json()["data"]["group_id"] == group_id

    # 传入不存在的用户组应报错
    bogus = client.patch(
        f"/api/admin/users/{bob['id']}",
        json={"group_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert bogus.status_code == 400

    # 解除分组（显式 null）
    cleared = client.patch(f"/api/admin/users/{bob['id']}", json={"group_id": None})
    assert cleared.json()["data"]["group_id"] is None
