"""DEK 管理器：信封加密的落地（见设计说明书 §3.2/§3.5）。

- ``DEK_key`` 由 KEK 包裹后落盘（``dek.key.enc``，600），进程内以 KeyRing 持有；
- 首次使用时惰性生成；支持代次轮换；
- 用户对话密钥 ``DEK_conv`` 由 KEK 直接包裹（存储于 users 表）。
"""

from __future__ import annotations

import os
from pathlib import Path

from app.core.crypto import cipher
from app.core.crypto.kek import KekProvider
from app.core.crypto.keyring import KeyRing
from app.core.errors import CipherError, KekLocked

API_KEY_DEK_AAD = b"dek-api-key"
CONV_DEK_AAD = b"dek-conversation"


def _atomic_write(path: Path, data: bytes, *, mode: int = 0o600) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    try:
        os.chmod(tmp, mode)
    except OSError:
        pass
    os.replace(tmp, path)


class KeyManager:
    def __init__(self, kek_provider: KekProvider, keys_dir: Path) -> None:
        self.kek = kek_provider
        self.keys_dir = Path(keys_dir)
        self.dek_file = self.keys_dir / "dek.key.enc"
        self.ring = KeyRing()
        self._loaded = False

    @property
    def loaded(self) -> bool:
        return self._loaded

    def reset(self) -> None:
        """主密钥锁定 / 轮换后清空内存中的 DEK。"""
        self.ring = KeyRing()
        self._loaded = False

    def ensure_loaded(self) -> None:
        if self._loaded:
            return
        if not self.kek.is_unlocked:
            raise KekLocked("主密钥未解锁，无法加载 DEK")

        self.keys_dir.mkdir(parents=True, exist_ok=True)
        if self.dek_file.exists():
            blob = self.dek_file.read_bytes()
            gen = cipher.key_gen_of(blob)
            dek = self.kek.unwrap(blob, aad=API_KEY_DEK_AAD)
            self.ring.add(gen, dek)
        else:
            dek = os.urandom(cipher.KEY_LEN)
            blob = self.kek.wrap(dek, key_gen=0, aad=API_KEY_DEK_AAD)
            _atomic_write(self.dek_file, blob)
            self.ring.add(0, dek)
        self._loaded = True

    def encrypt_secret(self, plaintext: str, *, aad: bytes = b"") -> bytes:
        self.ensure_loaded()
        return self.ring.encrypt(plaintext.encode("utf-8"), aad=aad)

    def decrypt_secret(self, blob: bytes, *, aad: bytes = b"") -> str:
        self.ensure_loaded()
        return self.ring.decrypt(blob, aad=aad).decode("utf-8")

    # --- 用户对话密钥 ---
    def new_conversation_key(self) -> tuple[bytes, bytes]:
        dek = os.urandom(cipher.KEY_LEN)
        return dek, self.kek.wrap(dek, key_gen=0, aad=CONV_DEK_AAD)

    def unwrap_conversation_key(self, wrapped: bytes) -> bytes:
        return self.kek.unwrap(wrapped, aad=CONV_DEK_AAD)

    # --- 供恢复码重置流程使用 ---
    def api_dek(self) -> tuple[int, bytes]:
        """返回当前代次与 DEK_key 明文（仅在内存中短暂使用）。"""
        self.ensure_loaded()
        generation = self.ring.latest
        return generation, self.ring.get(generation)

    def store_api_dek(self, dek: bytes, key_gen: int) -> None:
        """用当前 KEK 重新包裹并落盘 DEK_key（用于口令重置后重包裹）。"""
        blob = self.kek.wrap(dek, key_gen=key_gen, aad=API_KEY_DEK_AAD)
        _atomic_write(self.dek_file, blob)
        self.reset()
        self.ring.add(key_gen, dek)
        self._loaded = True

    # --- 轮换 ---
    def rotate_dek(self) -> int:
        """生成新代次 DEK_key，旧代次保留在内存 ring 中用于解密旧数据。"""
        self.ensure_loaded()
        new_gen = self.ring.latest + 1
        if new_gen > 0xFF:
            raise CipherError("密钥代次已用尽")
        dek = os.urandom(cipher.KEY_LEN)
        blob = self.kek.wrap(dek, key_gen=new_gen, aad=API_KEY_DEK_AAD)
        _atomic_write(self.dek_file, blob)
        self.ring.add(new_gen, dek)
        return new_gen
