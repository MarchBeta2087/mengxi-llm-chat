"""DEK 管理器单元测试。"""

from __future__ import annotations

import base64
import os

import pytest

from app.core.crypto.kek import Argon2Params, EnvKekProvider, LocalKekProvider
from app.core.errors import KekLocked
from app.services.key_manager import KeyManager

FAST = Argon2Params(time_cost=1, memory_cost=8192, parallelism=1, hash_len=32)


def _env_provider() -> EnvKekProvider:
    return EnvKekProvider(base64.urlsafe_b64encode(os.urandom(32)).decode(), FAST)


def test_roundtrip_and_file_created(tmp_path) -> None:
    manager = KeyManager(_env_provider(), tmp_path / "keys")
    blob = manager.encrypt_secret("sk-abc", aad=b"api-key:x")
    assert manager.dek_file.exists()
    assert manager.decrypt_secret(blob, aad=b"api-key:x") == "sk-abc"


def test_reload_unwraps_existing_dek(tmp_path) -> None:
    provider = _env_provider()
    keys_dir = tmp_path / "keys"
    first = KeyManager(provider, keys_dir)
    blob = first.encrypt_secret("sk-abc", aad=b"api-key:x")

    second = KeyManager(provider, keys_dir)
    assert second.decrypt_secret(blob, aad=b"api-key:x") == "sk-abc"


def test_rotate_keeps_old_readable(tmp_path) -> None:
    manager = KeyManager(_env_provider(), tmp_path / "keys")
    old = manager.encrypt_secret("sk-old", aad=b"a")
    new_gen = manager.rotate_dek()
    assert new_gen == 1
    new = manager.encrypt_secret("sk-new", aad=b"a")

    assert manager.decrypt_secret(old, aad=b"a") == "sk-old"
    assert manager.decrypt_secret(new, aad=b"a") == "sk-new"


def test_locked_provider_raises(tmp_path) -> None:
    provider = LocalKekProvider(tmp_path / "keys", FAST)
    manager = KeyManager(provider, tmp_path / "keys")
    with pytest.raises(KekLocked):
        manager.encrypt_secret("sk-abc")


def test_conversation_key_wrap_unwrap(tmp_path) -> None:
    manager = KeyManager(_env_provider(), tmp_path / "keys")
    dek, wrapped = manager.new_conversation_key()
    assert manager.unwrap_conversation_key(wrapped) == dek
