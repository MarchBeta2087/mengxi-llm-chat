"""三层兜底限流（用户/用户组/IP）与用户组配额。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import chat, create_key, login, promote_to_admin, register


def test_user_level_limit_blocks(client_factory) -> None:
    client = client_factory(user_rate_limits='{"rpm": 1}')
    register(client)
    create_key(client)

    assert "event: done" in chat(client)
    second = chat(client)
    assert "event: error" in second
    assert "用户级限流" in second
    assert '"dimension": "rpm"' in second


def test_ip_level_limit_blocks(client_factory) -> None:
    client = client_factory(ip_rate_limits='{"rpm": 1}')
    register(client)
    create_key(client)

    assert "event: done" in chat(client)
    assert "IP 级限流" in chat(client)


def test_three_tier_disabled_by_default(client_factory) -> None:
    client = client_factory()
    register(client)
    create_key(client)
    for _ in range(3):
        assert "event: done" in chat(client)


def test_group_quota_blocks(client: TestClient, db_path: Path) -> None:
    register(client, "admin")
    promote_to_admin(db_path, "admin")
    group = client.post("/api/admin/groups", json={"name": "g1", "daily_quota_tokens": 5}).json()[
        "data"
    ]

    register(client, "bob")
    login(client, "admin")
    bob = next(u for u in client.get("/api/admin/users").json()["data"] if u["username"] == "bob")
    client.patch(f"/api/admin/users/{bob['id']}", json={"group_id": group["id"]})
    login(client, "bob")

    create_key(client)
    assert "event: done" in chat(client)  # 消耗 8 tokens > 组配额 5
    second = chat(client)
    assert "event: error" in second
    assert "用户组配额已用完" in second
    assert '"code": 42901' in second


def test_redis_down_still_serves(client: TestClient) -> None:
    """Redis 不可用时降级：已登录用户仍能聊天（风险 R4）。"""
    from redis.exceptions import ConnectionError as RedisConnectionError

    class BrokenFacility:
        def __getattr__(self, _name: str):
            async def _boom(*_args, **_kwargs):
                raise RedisConnectionError("redis down")

            return _boom

    register(client)
    create_key(client)

    client.app.state.rate_limiter = BrokenFacility()
    client.app.state.circuit_breaker = BrokenFacility()

    body = chat(client)
    assert "event: done" in body
    assert '"text": "你好"' in body
