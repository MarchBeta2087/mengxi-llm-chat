"""主密钥提供者测试。"""

from __future__ import annotations

import base64
import os

import pytest

from app.core.crypto.kek import (
    Argon2Params,
    EnvKekProvider,
    KekState,
    LocalKekProvider,
)
from app.core.errors import KekLocked, WrongPassphrase

FAST = Argon2Params(time_cost=1, memory_cost=8192, parallelism=1, hash_len=32)
PASSPHRASE = "correct horse battery staple"


def test_env_provider_wrap_unwrap() -> None:
    key = os.urandom(32)
    provider = EnvKekProvider(base64.urlsafe_b64encode(key).decode(), FAST)
    assert provider.state == KekState.UNLOCKED
    dek = os.urandom(32)
    wrapped = provider.wrap(dek, key_gen=2)
    assert provider.unwrap(wrapped) == dek


def test_env_provider_rejects_bad_length() -> None:
    with pytest.raises(ValueError):
        EnvKekProvider(base64.urlsafe_b64encode(b"short").decode(), FAST)


async def test_local_provider_lifecycle(tmp_path) -> None:
    provider = LocalKekProvider(tmp_path, FAST)
    assert provider.state == KekState.UNINITIALIZED

    await provider.initialize(PASSPHRASE)
    assert provider.state == KekState.UNLOCKED

    wrapped = provider.wrap(os.urandom(32))
    provider.lock()
    assert provider.state == KekState.LOCKED
    with pytest.raises(KekLocked):
        provider.wrap(b"x" * 32)

    await provider.unlock(PASSPHRASE)
    assert provider.is_unlocked
    assert provider.unwrap(wrapped)


async def test_local_provider_wrong_passphrase(tmp_path) -> None:
    provider = LocalKekProvider(tmp_path, FAST)
    await provider.initialize("right-passphrase")
    provider.lock()
    with pytest.raises(WrongPassphrase):
        await provider.unlock("wrong-passphrase")
    assert not provider.is_unlocked


async def test_local_provider_double_initialize_rejected(tmp_path) -> None:
    provider = LocalKekProvider(tmp_path, FAST)
    await provider.initialize(PASSPHRASE)
    with pytest.raises(ValueError):
        await provider.initialize(PASSPHRASE)
