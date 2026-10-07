"""审计查询接口测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from ipaddress import ip_address
from pathlib import Path

from fastapi.testclient import TestClient

from app.schemas.admin import AuditRead
from tests.conftest import chat, create_key, login, promote_to_admin, register


def test_self_audit_returns_own_records(client: TestClient) -> None:
    register(client)
    create_key(client)
    chat(client)

    logs = client.get("/api/audit").json()["data"]
    assert len(logs) == 1
    assert logs[0]["status"] == 200
    assert logs[0]["tokens_in"] == 5
    assert logs[0]["tokens_out"] == 3
    assert logs[0]["base_url_host"] == "api.openai.com"
    assert logs[0]["fallback_to_public"] is False


def test_self_audit_is_isolated(client: TestClient) -> None:
    register(client, "alice")
    create_key(client)
    chat(client)

    register(client, "bob")
    assert client.get("/api/audit").json()["data"] == []


def test_admin_audit_and_filters(client: TestClient, db_path: Path) -> None:
    register(client, "admin")
    promote_to_admin(db_path, "admin")
    create_key(client)
    chat(client)

    login(client, "admin")
    all_logs = client.get("/api/admin/audit").json()["data"]
    assert len(all_logs) == 1

    ok = client.get("/api/admin/audit", params={"status": 200}).json()["data"]
    assert len(ok) == 1

    none = client.get("/api/admin/audit", params={"status": 500}).json()["data"]
    assert none == []

    fallback = client.get("/api/admin/audit", params={"fallback_only": True}).json()["data"]
    assert fallback == []


def test_admin_audit_requires_admin(client: TestClient) -> None:
    register(client, "bob")
    assert client.get("/api/admin/audit").status_code == 403


def test_admin_audit_export_csv(client: TestClient, db_path: Path) -> None:
    register(client, "admin")
    promote_to_admin(db_path, "admin")
    create_key(client)
    chat(client)

    login(client, "admin")
    resp = client.get("/api/admin/audit/export")
    assert resp.status_code == 200, resp.text
    assert "text/csv" in resp.headers["content-type"]
    assert "attachment" in resp.headers.get("content-disposition", "")
    lines = [line for line in resp.text.splitlines() if line]
    assert lines[0].split(",")[:3] == ["id", "created_at", "user_id"]
    assert len(lines) >= 2  # 表头 + 至少一条记录


def test_admin_audit_export_requires_admin(client: TestClient) -> None:
    register(client, "bob")
    assert client.get("/api/admin/audit/export").status_code == 403


def test_audit_read_accepts_ip_address_object() -> None:
    """PostgreSQL INET 可能返回 ipaddress 对象，AuditRead 应兼容（回归）。"""
    model = AuditRead(
        id=1,
        user_id=None,
        key_id=None,
        key_type="private",
        model="gpt-4o",
        base_url_host="api.example.com",
        tokens_in=1,
        tokens_out=2,
        latency_ms=3,
        status=200,
        fallback_to_public=False,
        client_ip=ip_address("203.0.113.5"),
        created_at=datetime.now(UTC),
    )
    assert model.client_ip == "203.0.113.5"
    assert model.model_dump(mode="json")["client_ip"] == "203.0.113.5"
