"""会话与消息接口测试：透明加解密、持久化、盲索引搜索。"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import create_key, register

SECRET = "sk-conv-secret-0000zzzz"


def _create_key(client: TestClient) -> dict:
    return create_key(client, api_key=SECRET, models=["gpt-4o"])


def _chat(client: TestClient, content: str, conversation_id: str | None = None) -> str:
    body: dict = {"model": "gpt-4o", "messages": [{"role": "user", "content": content}]}
    if conversation_id:
        body["conversation_id"] = conversation_id
    with client.stream("POST", "/api/chat/completions", json=body) as resp:
        assert resp.status_code == 200, resp.text
        return "".join(resp.iter_text())


def _conversation_id(sse_body: str) -> str:
    meta = re.search(r"event: meta\ndata: (\{.*?\})\n", sse_body)
    assert meta, sse_body
    return json.loads(meta.group(1))["conversation_id"]


def test_conversation_crud_and_isolation(client: TestClient) -> None:
    register(client, "alice")
    created = client.post("/api/conversations", json={"title": "第一篇"}).json()["data"]
    assert created["title"] == "第一篇"
    assert client.get("/api/conversations").json()["data"][0]["id"] == created["id"]

    renamed = client.patch(f"/api/conversations/{created['id']}", json={"title": "改名"}).json()[
        "data"
    ]
    assert renamed["title"] == "改名"
    assert client.delete(f"/api/conversations/{created['id']}").status_code == 200

    other = client.post("/api/conversations", json={}).json()["data"]
    client.post("/api/auth/logout")
    register(client, "bob")
    assert client.get(f"/api/conversations/{other['id']}/messages").status_code == 403


def test_chat_persists_encrypted_messages(client: TestClient, db_path: Path) -> None:
    register(client)
    _create_key(client)
    plaintext = "请记住这句独一无二的话：星河灿烂"
    body = _chat(client, plaintext)
    conversation_id = _conversation_id(body)
    assert conversation_id

    messages = client.get(f"/api/conversations/{conversation_id}/messages").json()["data"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["content"] == plaintext
    assert messages[1]["content"] == "你好，世界"

    # 数据库内不得出现任何明文
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT content_encrypted FROM messages").fetchall()
    finally:
        conn.close()
    assert rows
    for (content_encrypted,) in rows:
        assert plaintext not in content_encrypted
        assert "你好" not in content_encrypted


def test_chat_uses_conversation_context(client: TestClient) -> None:
    from tests.conftest import FakeUpstreamClient

    register(client)
    _create_key(client)
    first = _chat(client, "第一轮")
    conversation_id = _conversation_id(first)

    _chat(client, "第二轮", conversation_id=conversation_id)
    payload = FakeUpstreamClient.calls[-1]["payload"]["messages"]
    roles = [m["role"] for m in payload]
    # 历史（user/assistant） + 本轮 user
    assert roles == ["user", "assistant", "user"]
    assert payload[-1]["content"] == "第二轮"


def test_blind_index_search_and_no_plaintext(client_factory, db_path: Path) -> None:
    client = client_factory(encrypted_search=True)
    register(client)
    _create_key(client)
    body = _chat(client, "我们要讨论量子纠缠与quantumleap")
    conversation_id = _conversation_id(body)

    hits = client.get("/api/conversations/search", params={"q": "量子"}).json()["data"]
    assert any(h["conversation_id"] == conversation_id and h["kind"] == "message" for h in hits)

    english = client.get("/api/conversations/search", params={"q": "quantumleap"}).json()["data"]
    assert english

    # 盲索引表不得含明文关键词
    conn = sqlite3.connect(db_path)
    try:
        fps = conn.execute("SELECT keyword_fp FROM message_keywords").fetchall()
    finally:
        conn.close()
    assert fps
    for (fp,) in fps:
        assert "量子" not in fp.decode("latin-1", "ignore")


def test_search_title_only_when_index_disabled(client: TestClient) -> None:
    register(client)
    client.post("/api/conversations", json={"title": "关于黑洞的讨论"})
    hits = client.get("/api/conversations/search", params={"q": "黑洞"}).json()["data"]
    assert len(hits) == 1
    assert hits[0]["kind"] == "title"
