"""主密钥（KEK）提供者：档 A 口令派生 / 档 B 环境变量 / 档 C KMS（见设计说明书 §3.3）。

KEK 只负责包裹与解包 DEK，不直接加密业务数据。
"""

from __future__ import annotations

import base64
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from argon2.low_level import Type, hash_secret_raw

from app.core.config import Settings
from app.core.crypto import cipher
from app.core.errors import CipherError, KekLocked, WrongPassphrase

VERIFIER_PLAINTEXT = b"mengxi-kek-verifier-v1"
KEK_VERIFY_AAD = b"kek-verify"
DEK_AAD = b"dek"


class KekState(StrEnum):
    UNINITIALIZED = "uninitialized"
    LOCKED = "locked"
    UNLOCKED = "unlocked"


@dataclass(frozen=True)
class Argon2Params:
    time_cost: int = 3
    memory_cost: int = 65536
    parallelism: int = 4
    hash_len: int = 32
    salt_len: int = 16

    def derive(self, passphrase: str | bytes, salt: bytes) -> bytes:
        secret = passphrase.encode("utf-8") if isinstance(passphrase, str) else passphrase
        return hash_secret_raw(
            secret=secret,
            salt=salt,
            time_cost=self.time_cost,
            memory_cost=self.memory_cost,
            parallelism=self.parallelism,
            hash_len=self.hash_len,
            type=Type.ID,
        )


class KekProvider(ABC):
    """主密钥提供者抽象。"""

    profile: str = "?"

    def __init__(self, params: Argon2Params | None = None) -> None:
        self.params = params or Argon2Params()
        self._kek: bytes | None = None

    # --- 状态 ---
    def _is_materialized(self) -> bool:
        """底层密钥材料是否已存在（用于区分 UNINITIALIZED / LOCKED）。"""
        return False

    @property
    def state(self) -> KekState:
        if self._kek is not None:
            return KekState.UNLOCKED
        return KekState.LOCKED if self._is_materialized() else KekState.UNINITIALIZED

    @property
    def kek(self) -> bytes:
        if self._kek is None:
            raise KekLocked("主密钥尚未解锁")
        return self._kek

    @property
    def is_unlocked(self) -> bool:
        return self._kek is not None

    def install_kek(self, kek: bytes) -> None:
        """直接安装 KEK（供恢复码流程在内存中临时使用）。"""
        if len(kek) != cipher.KEY_LEN:
            raise ValueError(f"KEK must be {cipher.KEY_LEN} bytes")
        self._kek = kek

    def lock(self) -> None:
        self._kek = None

    # --- 生命周期 ---
    @abstractmethod
    async def initialize(self, passphrase: str | None = None) -> None:
        """首次初始化主密钥材料。"""

    @abstractmethod
    async def unlock(self, passphrase: str | None = None) -> None:
        """解锁主密钥（档 A 需要口令，档 B 为空操作）。"""

    # --- 包裹 DEK ---
    def wrap(self, plaintext_key: bytes, *, key_gen: int = 0, aad: bytes = DEK_AAD) -> bytes:
        return cipher.encrypt(self.kek, plaintext_key, key_gen=key_gen, aad=aad)

    def unwrap(self, blob: bytes, *, aad: bytes = DEK_AAD) -> bytes:
        return cipher.decrypt(key=self.kek, blob=blob, aad=aad)

    def status(self) -> dict[str, object]:
        return {"profile": self.profile, "state": self.state.value, "unlocked": self.is_unlocked}


def _atomic_write(path: Path, data: bytes, *, mode: int = 0o600) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    try:
        os.chmod(tmp, mode)
    except OSError:
        pass  # 非 POSIX 平台忽略
    os.replace(tmp, path)


class LocalKekProvider(KekProvider):
    """档 A：管理员口令经 Argon2id 派生 KEK；重启后需重新解锁。"""

    profile = "A"

    def __init__(self, keys_dir: Path, params: Argon2Params | None = None) -> None:
        super().__init__(params)
        self.keys_dir = Path(keys_dir)
        self.salt_file = self.keys_dir / "kek.salt"
        self.verifier_file = self.keys_dir / "kek.verify"

    def _is_materialized(self) -> bool:
        return self.salt_file.exists() and self.verifier_file.exists()

    async def initialize(self, passphrase: str | None = None) -> None:
        if not passphrase:
            raise ValueError("档 A 初始化需要主口令")
        if self._is_materialized():
            raise ValueError("主密钥已初始化")

        self.keys_dir.mkdir(parents=True, exist_ok=True)
        salt = os.urandom(self.params.salt_len)
        kek = self.params.derive(passphrase, salt)
        verifier = cipher.encrypt(kek, VERIFIER_PLAINTEXT, key_gen=0, aad=KEK_VERIFY_AAD)

        _atomic_write(self.salt_file, salt)
        _atomic_write(self.verifier_file, verifier)
        self._kek = kek

    async def unlock(self, passphrase: str | None = None) -> None:
        if not passphrase:
            raise ValueError("档 A 解锁需要主口令")
        if not self._is_materialized():
            raise ValueError("主密钥尚未初始化")

        salt = self.salt_file.read_bytes()
        kek = self.params.derive(passphrase, salt)
        verifier = self.verifier_file.read_bytes()
        try:
            cipher.decrypt(key=kek, blob=verifier, aad=KEK_VERIFY_AAD)
        except CipherError as exc:
            raise WrongPassphrase("主口令错误") from exc
        self._kek = kek

    async def reinitialize(self, passphrase: str) -> None:
        """用新口令重新派生 KEK 并覆盖盐/校验文件（恢复码重置流程使用）。"""
        self.keys_dir.mkdir(parents=True, exist_ok=True)
        salt = os.urandom(self.params.salt_len)
        kek = self.params.derive(passphrase, salt)
        verifier = cipher.encrypt(kek, VERIFIER_PLAINTEXT, key_gen=0, aad=KEK_VERIFY_AAD)
        _atomic_write(self.salt_file, salt)
        _atomic_write(self.verifier_file, verifier)
        self._kek = kek


class EnvKekProvider(KekProvider):
    """档 B：主密钥来自环境变量，启动即处于已解锁状态。"""

    profile = "B"

    def __init__(self, master_key_b64: str, params: Argon2Params | None = None) -> None:
        super().__init__(params)
        padded = master_key_b64 + "=" * (-len(master_key_b64) % 4)
        try:
            key = base64.urlsafe_b64decode(padded)
        except Exception as exc:  # noqa: BLE001
            raise ValueError("MENGXI_MASTER_KEY_B64 不是合法的 base64") from exc
        if len(key) != cipher.KEY_LEN:
            raise ValueError(f"档 B 主密钥必须为 {cipher.KEY_LEN} 字节")
        self._kek = key

    def _is_materialized(self) -> bool:
        return True

    async def initialize(self, passphrase: str | None = None) -> None:
        if self._kek is None:
            raise ValueError("档 B 主密钥缺失")

    async def unlock(self, passphrase: str | None = None) -> None:
        if self._kek is None:
            raise ValueError("档 B 主密钥缺失")


class KmsKekProvider(KekProvider):
    """档 C：外部 KMS 托管 KEK（M5 接入，先占位）。"""

    profile = "C"

    async def initialize(self, passphrase: str | None = None) -> None:
        raise NotImplementedError("KMS 档 C 将在 M5 实现")

    async def unlock(self, passphrase: str | None = None) -> None:
        raise NotImplementedError("KMS 档 C 将在 M5 实现")


def argon_params_from_settings(settings: Settings) -> Argon2Params:
    return Argon2Params(
        time_cost=settings.argon2_time_cost,
        memory_cost=settings.argon2_memory_cost,
        parallelism=settings.argon2_parallelism,
        hash_len=settings.argon2_hash_len,
    )


def build_kek_provider(settings: Settings) -> KekProvider:
    params = argon_params_from_settings(settings)
    if settings.kek_profile == "A":
        return LocalKekProvider(settings.keys_dir, params)
    if settings.kek_profile == "B":
        if not settings.master_key_b64:
            raise ValueError("档 B 需要环境变量 MENGXI_MASTER_KEY_B64")
        return EnvKekProvider(settings.master_key_b64, params)
    return KmsKekProvider(params)
