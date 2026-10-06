"""盲索引领域测试。"""

from __future__ import annotations

from app.domain.blind_index import (
    derive_index_key,
    fingerprint,
    fingerprints,
    tokenize,
)


def test_tokenize_english_and_chinese() -> None:
    tokens = tokenize("Hello quantum 量子纠缠 a 我")
    assert "hello" in tokens
    assert "quantum" in tokens
    assert "量子" in tokens
    assert "子纠" in tokens
    assert "纠缠" in tokens
    assert "a" not in tokens  # 长度 < 2 丢弃
    assert "我" not in tokens


def test_derive_index_key_is_stable_and_distinct() -> None:
    key = derive_index_key(b"secret")
    assert key == derive_index_key(b"secret")
    assert key != derive_index_key(b"other")
    assert len(key) == 32


def test_fingerprint_is_deterministic_and_opaque() -> None:
    key = derive_index_key(b"secret")
    fp = fingerprint(key, "量子")
    assert fp == fingerprint(key, "量子")
    assert len(fp) == 32
    assert "量子".encode() not in fp


def test_fingerprints_set() -> None:
    key = derive_index_key(b"secret")
    assert len(fingerprints(key, "量子量子")) == len(tokenize("量子量子"))
