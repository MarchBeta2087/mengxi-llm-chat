"""恢复码接口测试（档 A 全流程）。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import create_key, login, promote_to_admin, register

PASSPHRASE = "initial-pass-123"


def _chat(client: TestClient, content: str, model: str = "gpt-4o") -> str:
    with client.stream(
        "POST",
        "/api/chat/completions",
        json={"model": model, "messages": [{"role": "user", "content": content}]},
    ) as resp:
        assert resp.status_code == 200, resp.text
        return "".join(resp.iter_text())


def _conversation_id(sse_body: str) -> str:
    match = re.search(r"event: meta\ndata: (\{.*?\})\n", sse_body)
    assert match, sse_body
    return json.loads(match.group(1))["conversation_id"]


def _admin_client(client_factory) -> TestClient:
    client = client_factory(
        kek_profile="A",
        master_key_b64=None,
        argon2_time_cost=1,
        argon2_memory_cost=8192,
        argon2_parallelism=1,
    )
    register(client, "admin")
    return client


def test_recovery_full_flow(client_factory, db_path: Path) -> None:
    client = _admin_client(client_factory)
    promote_to_admin(db_path, "admin")
    login(client, "admin")

    # 初始化主密钥并一次性拿到恢复码
    init = client.post("/api/admin/kek/initialize", json={"passphrase": PASSPHRASE})
    assert init.status_code == 200, init.text
    codes = init.json()["data"]["recovery_codes"]
    assert len(codes) == 8
    assert client.get("/api/admin/recovery-codes").json()["data"]["remaining"] == 8

    # 制造加密数据：API Key + 一条会话消息
    create_key(client, api_key="sk-recovery-0000zzzz", models=["gpt-4o"])
    body = _chat(client, "恢复码测试前的消息")
    conversation_id = _conversation_id(body)

    # 使用恢复码重置主口令
    used = codes[0]
    reset = client.post(
        "/api/admin/recovery-codes/use",
        json={"code": used, "new_passphrase": "brand-new-pass-456"},
    )
    assert reset.status_code == 200, reset.text
    new_codes = reset.json()["data"]["codes"]
    assert len(new_codes) == 8
    assert used not in new_codes
    assert client.get("/api/admin/recovery-codes").json()["data"]["remaining"] == 8

    # 旧码立即失效
    reuse = client.post(
        "/api/admin/recovery-codes/use",
        json={"code": used, "new_passphrase": "another-pass-789"},
    )
    assert reuse.status_code == 401

    # 重置后旧数据仍可解密（DEK 已重包裹）
    messages = client.get(f"/api/conversations/{conversation_id}/messages").json()["data"]
    assert messages[0]["content"] == "恢复码测试前的消息"

    # 重置后仍能解密 API Key 并完成一次对话
    assert "event: done" in _chat(client, "重置口令之后还能继续聊吗")


def test_recovery_wrong_code_rejected(client_factory, db_path: Path) -> None:
    client = _admin_client(client_factory)
    promote_to_admin(db_path, "admin")
    login(client, "admin")
    client.post("/api/admin/kek/initialize", json={"passphrase": PASSPHRASE})

    resp = client.post(
        "/api/admin/recovery-codes/use",
        json={"code": "ZZZZ-ZZZZ-ZZZZ", "new_passphrase": "whatever-pass-1"},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == 40101


def test_recovery_regenerate_invalidates_all(client_factory, db_path: Path) -> None:
    client = _admin_client(client_factory)
    promote_to_admin(db_path, "admin")
    login(client, "admin")
    init = client.post("/api/admin/kek/initialize", json={"passphrase": PASSPHRASE})
    old_codes = init.json()["data"]["recovery_codes"]

    regenerated = client.post("/api/admin/recovery-codes/regenerate")
    assert regenerated.status_code == 200
    new_codes = regenerated.json()["data"]["codes"]
    assert set(old_codes).isdisjoint(new_codes)

    # 旧码不可再用
    assert (
        client.post(
            "/api/admin/recovery-codes/use",
            json={"code": old_codes[0], "new_passphrase": "whatever-pass-2"},
        ).status_code
        == 401
    )
