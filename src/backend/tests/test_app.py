"""应用装配冒烟测试。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.conftest import login, promote_to_admin, register


def test_healthz(tmp_path) -> None:
    app = create_app(Settings(kek_profile="A", data_dir=tmp_path))
    with TestClient(app) as client:
        resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_security_headers(tmp_path) -> None:
    app = create_app(Settings(kek_profile="A", data_dir=tmp_path))
    with TestClient(app) as client:
        health = client.get("/healthz")
        api = client.get("/api/__headers_probe__")

    for resp in (health, api):
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert "camera=()" in resp.headers["Permissions-Policy"]

    # API 施加最严格 CSP；非 API 路径不施加（避免破坏 /docs 等页面）
    assert health.headers.get("Content-Security-Policy") is None
    assert api.headers["Content-Security-Policy"].startswith("default-src 'none'")


def test_kek_status_uninitialized(client_factory, db_path: Path) -> None:
    client = client_factory(kek_profile="A", master_key_b64=None)
    register(client, "admin")
    promote_to_admin(db_path, "admin")
    login(client, "admin")

    resp = client.get("/api/admin/kek")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["profile"] == "A"
    assert body["data"]["state"] == "uninitialized"


def test_mengxi_error_maps_to_payload(tmp_path) -> None:
    from app.core.errors import SsrfRejected

    app = create_app(Settings(kek_profile="A", data_dir=tmp_path))

    @app.get("/_boom")
    async def _boom() -> None:  # pragma: no cover - 测试用路由
        raise SsrfRejected("阻止访问内网", target="169.254.169.254")

    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/_boom")
    assert resp.status_code == 400
    assert resp.json()["code"] == 40010
    assert resp.json()["target"] == "169.254.169.254"
