"""加密子系统单元测试。"""

from __future__ import annotations

import os

import pytest

from app.core.crypto import cipher
from app.core.crypto.keyring import KeyRing
from app.core.errors import CipherError

KEY = os.urandom(32)
OTHER = os.urandom(32)


def test_encrypt_decrypt_roundtrip() -> None:
    blob = cipher.encrypt(KEY, "你好，梦溪".encode(), key_gen=3, aad=b"msg:c1")
    assert cipher.decrypt(key=KEY, blob=blob, aad=b"msg:c1").decode() == "你好，梦溪"


def test_header_layout_and_length() -> None:
    plaintext = b"hello"
    blob = cipher.encrypt(KEY, plaintext, key_gen=7)
    assert blob[0] == cipher.ALG_AES_256_GCM
    assert blob[1] == 7
    assert cipher.peek_header(blob) == (cipher.ALG_AES_256_GCM, 7)
    assert cipher.key_gen_of(blob) == 7
    assert len(blob) == cipher.HEADER_LEN + cipher.IV_LEN + len(plaintext) + cipher.TAG_LEN


def test_iv_is_unique_per_encryption() -> None:
    blobs = [cipher.encrypt(KEY, b"same", key_gen=0) for _ in range(50)]
    ivs = {b[cipher.HEADER_LEN : cipher.HEADER_LEN + cipher.IV_LEN] for b in blobs}
    assert len(ivs) == len(blobs)


def test_aad_is_bound() -> None:
    blob = cipher.encrypt(KEY, b"secret", key_gen=0, aad=b"ctx-a")
    with pytest.raises(CipherError):
        cipher.decrypt(key=KEY, blob=blob, aad=b"ctx-b")


def test_header_tamper_detected() -> None:
    blob = bytearray(cipher.encrypt(KEY, b"secret", key_gen=1))
    blob[1] = 2  # 篡改 key_gen，AAD 认证应失败
    with pytest.raises(CipherError):
        cipher.decrypt(key=KEY, blob=bytes(blob))


def test_wrong_key_fails() -> None:
    blob = cipher.encrypt(KEY, b"secret")
    with pytest.raises(CipherError):
        cipher.decrypt(key=OTHER, blob=blob)


def test_short_blob_rejected() -> None:
    with pytest.raises(CipherError):
        cipher.decrypt(key=KEY, blob=b"\x01")


def test_key_length_validated() -> None:
    with pytest.raises(ValueError):
        cipher.encrypt(b"short", b"x")


def test_keyring_rotation_selects_generation() -> None:
    ring = KeyRing()
    ring.add(0, os.urandom(32))
    old = ring.encrypt(b"old", key_gen=0)
    ring.add(1, os.urandom(32))
    new = ring.encrypt(b"new")
    assert cipher.key_gen_of(new) == 1
    assert ring.decrypt(old) == b"old"
    assert ring.decrypt(new) == b"new"
    assert ring.generations == (0, 1)


def test_keyring_missing_generation() -> None:
    ring = KeyRing()
    ring.add(0, os.urandom(32))
    blob = ring.encrypt(b"x")
    ring.remove(0)
    with pytest.raises(CipherError):
        ring.decrypt(blob)
