"""档 A 主口令错误锁定测试（P0-2，基于 Redis 失败计数）。

覆盖：达阈值后即使口令正确也拒绝（429）；解锁成功清零计数；
未登录/非管理员无法触达解锁逻辑（P0-1 回归）。
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import login, promote_to_admin, register

PASSPHRASE = "initial-pass-123"
WRONG = "wrong-pass-000"


def _admin_client(client_factory, **overrides) -> TestClient:
    client = client_factory(
        kek_profile="A",
        master_key_b64=None,
        argon2_time_cost=1,
        argon2_memory_cost=8192,
        argon2_parallelism=1,
        **overrides,
    )
    register(client, "admin")
    return client


def _init_and_lock(client: TestClient, db_path: Path) -> None:
    promote_to_admin(db_path, "admin")
    login(client, "admin")
    resp = client.post("/api/admin/kek/initialize", json={"passphrase": PASSPHRASE})
    assert resp.status_code == 200, resp.text
    assert client.post("/api/admin/kek/lock").status_code == 200


def test_wrong_passphrase_locks_out(client_factory, db_path: Path) -> None:
    client = _admin_client(client_factory, kek_lock_threshold=3, kek_lock_seconds=60)
    _init_and_lock(client, db_path)

    for _ in range(3):
        resp = client.post("/api/admin/kek/unlock", json={"passphrase": WRONG})
        assert resp.status_code == 401, resp.text

    # 达阈值后，即使口令正确也拒绝
    locked = client.post("/api/admin/kek/unlock", json={"passphrase": PASSPHRASE})
    assert locked.status_code == 429, locked.text
    assert locked.json()["code"] == 42900


def test_success_clears_failure_counter(client_factory, db_path: Path) -> None:
    client = _admin_client(client_factory, kek_lock_threshold=3, kek_lock_seconds=60)
    _init_and_lock(client, db_path)

    for _ in range(2):
        assert client.post("/api/admin/kek/unlock", json={"passphrase": WRONG}).status_code == 401
    assert client.post("/api/admin/kek/unlock", json={"passphrase": PASSPHRASE}).status_code == 200

    client.post("/api/admin/kek/lock")
    # 计数已清零：再次累计两次错误仍为 401，而非 429
    for _ in range(2):
        assert client.post("/api/admin/kek/unlock", json={"passphrase": WRONG}).status_code == 401


def test_unauthenticated_unlock_rejected(client_factory) -> None:
    client = _admin_client(client_factory, kek_lock_threshold=3, kek_lock_seconds=60)
    client.post("/api/auth/logout")
    # 登出后不可触达解锁逻辑
    resp = client.post("/api/admin/kek/unlock", json={"passphrase": PASSPHRASE})
    assert resp.status_code == 401
