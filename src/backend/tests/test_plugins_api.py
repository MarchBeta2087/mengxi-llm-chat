"""插件 API 与沙箱集成测试。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import login, promote_to_admin, register

BUILTIN = Path(__file__).resolve().parents[2] / "plugins"


def _seed_admin(client: TestClient, db_path: Path) -> None:
    register(client, "admin")
    promote_to_admin(db_path, "admin")


def _install(client: TestClient, name: str, manifest_overrides: dict | None = None) -> dict:
    src = BUILTIN / name
    manifest = json.loads((src / "manifest.json").read_text(encoding="utf-8"))
    if manifest_overrides:
        manifest.update(manifest_overrides)
    code = (src / manifest.get("entry", "main.py")).read_text(encoding="utf-8")
    resp = client.post("/api/admin/plugins", json={"manifest": manifest, "code": code})
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def _install_code(client: TestClient, manifest: dict, code: str) -> dict:
    resp = client.post("/api/admin/plugins", json={"manifest": manifest, "code": code})
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def test_non_admin_cannot_install(client: TestClient) -> None:
    register(client, "bob")
    assert client.get("/api/admin/plugins").status_code == 403
    body = {
        "manifest": {"name": "probe", "version": "1.0.0", "entry": "main.py"},
        "code": "pass",
    }
    assert client.post("/api/admin/plugins", json=body).status_code == 403


def test_install_and_resolved_state(client: TestClient, db_path: Path) -> None:
    _seed_admin(client, db_path)
    plugin = _install(client, "echo")
    plugin_id = plugin["id"]
    assert plugin["type"] == "optional"

    # 普通用户默认禁用
    register(client, "bob")
    listed = client.get("/api/plugins").json()["data"]
    echo = next(p for p in listed if p["id"] == plugin_id)
    assert echo["enabled"] is False
    assert echo["state_source"] == "default"

    # 个人启用
    resp = client.post(f"/api/plugins/{plugin_id}/toggle", json={"enabled": True})
    assert resp.status_code == 200, resp.text
    echo = next(p for p in resp.json()["data"] if p["id"] == plugin_id)
    assert echo["enabled"] is True
    assert echo["state_source"] == "user"


def test_global_plugin_cannot_be_toggled(client: TestClient, db_path: Path) -> None:
    _seed_admin(client, db_path)
    plugin = _install(client, "echo")
    client.patch(f"/api/admin/plugins/{plugin['id']}", json={"type": "global"})

    register(client, "bob")
    listed = client.get("/api/plugins").json()["data"]
    echo = next(p for p in listed if p["id"] == plugin["id"])
    assert echo["enabled"] is True
    assert echo["state_source"] == "global"

    denied = client.post(f"/api/plugins/{plugin['id']}/toggle", json={"enabled": False})
    assert denied.status_code == 403


def test_group_config_overrides_user(client: TestClient, db_path: Path) -> None:
    _seed_admin(client, db_path)
    plugin = _install(client, "echo")
    group = client.post("/api/admin/groups", json={"name": "研发组"}).json()["data"]

    # 组内默认启用
    set_resp = client.put(
        f"/api/admin/groups/{group['id']}/plugins/{plugin['id']}", json={"state": "enabled"}
    )
    assert set_resp.status_code == 200, set_resp.text

    register(client, "bob")
    login(client, "admin")
    bob = next(u for u in client.get("/api/admin/users").json()["data"] if u["username"] == "bob")
    client.patch(f"/api/admin/users/{bob['id']}", json={"group_id": group["id"]})

    login(client, "bob")
    # 个人即使显式禁用，组配置仍优先
    client.post(f"/api/plugins/{plugin['id']}/toggle", json={"enabled": False})
    listed = client.get("/api/plugins").json()["data"]
    echo = next(p for p in listed if p["id"] == plugin["id"])
    assert echo["enabled"] is True
    assert echo["state_source"] == "group"


def test_invoke_echo_plugin(client: TestClient, db_path: Path) -> None:
    _seed_admin(client, db_path)
    plugin = _install(client, "echo")
    resp = client.post(
        f"/api/admin/plugins/{plugin['id']}/invoke", json={"input": {"text": "你好，沙箱"}}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["output"] == "你好，沙箱"


def test_permission_denied_without_http_permission(client: TestClient, db_path: Path) -> None:
    _seed_admin(client, db_path)
    manifest = {
        "name": "no-perm",
        "version": "1.0.0",
        "type": "optional",
        "entry": "main.py",
        "permissions": [],
        "runtime": {"timeout_ms": 5000, "memory_mb": 64, "cpu_seconds": 2},
    }
    code = (
        "import json,sys\n"
        "sys.stdin.readline()\n"
        "sys.stdout.write(json.dumps({'type':'http','id':1,'method':'GET',"
        "'url':'https://example.com'})+'\\n')\n"
        "sys.stdout.flush()\n"
        "sys.stdin.readline()\n"
    )
    plugin = _install_code(client, manifest, code)
    resp = client.post(f"/api/admin/plugins/{plugin['id']}/invoke", json={"input": {}})
    assert resp.status_code == 403
    assert resp.json()["code"] == 40310


def test_http_fetch_blocked_by_ssrf(client: TestClient, db_path: Path) -> None:
    """即使声明了 http:outbound:*，内网/元数据地址仍被 SSRF 拦截。"""
    _seed_admin(client, db_path)
    plugin = _install(client, "http-fetch")
    resp = client.post(
        f"/api/admin/plugins/{plugin['id']}/invoke",
        json={"input": {"url": "https://169.254.169.254/latest/meta-data"}},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == 40010


def test_plugin_timeout_killed(client: TestClient, db_path: Path) -> None:
    _seed_admin(client, db_path)
    manifest = {
        "name": "slow",
        "version": "1.0.0",
        "type": "optional",
        "entry": "main.py",
        "permissions": [],
        "runtime": {"timeout_ms": 300, "memory_mb": 64, "cpu_seconds": 2},
    }
    code = "import time\ntime.sleep(30)\n"
    plugin = _install_code(client, manifest, code)
    resp = client.post(f"/api/admin/plugins/{plugin['id']}/invoke", json={"input": {}})
    assert resp.status_code == 500
    assert resp.json()["code"] == 50011


def test_invalid_manifest_rejected(client: TestClient, db_path: Path) -> None:
    _seed_admin(client, db_path)
    bad = {"manifest": {"name": "Bad Name!"}, "code": "print('x')"}
    resp = client.post("/api/admin/plugins", json=bad)
    assert resp.status_code == 422
