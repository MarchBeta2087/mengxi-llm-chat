"""密钥环：按 ``key_gen`` 代次管理 DEK，支持不停机轮换（见设计说明书 §3.6）。

encrypt(...)  默认使用最新代次写入（key_gen 累加）
decrypt(...)  读取密文头中的 key_gen 选对应代次，无需试错解密
"""

from __future__ import annotations

from app.core.crypto import cipher
from app.core.errors import CipherError

_MAX_KEY_GEN = 0xFF


class KeyRing:
    def __init__(self) -> None:
        self._keys: dict[int, bytes] = {}

    def add(self, key_gen: int, key: bytes) -> None:
        if len(key) != cipher.KEY_LEN:
            raise ValueError(f"DEK must be {cipher.KEY_LEN} bytes")
        if not 0 <= key_gen <= _MAX_KEY_GEN:
            raise ValueError(f"key_gen out of range [0, {_MAX_KEY_GEN}]: {key_gen}")
        self._keys[key_gen] = key

    def remove(self, key_gen: int) -> None:
        self._keys.pop(key_gen, None)

    def has(self, key_gen: int) -> bool:
        return key_gen in self._keys

    @property
    def generations(self) -> tuple[int, ...]:
        return tuple(sorted(self._keys))

    @property
    def latest(self) -> int:
        if not self._keys:
            raise CipherError("key ring is empty")
        return max(self._keys)

    def encrypt(self, plaintext: bytes, *, key_gen: int | None = None, aad: bytes = b"") -> bytes:
        gen = self.latest if key_gen is None else key_gen
        if gen not in self._keys:
            raise CipherError(f"no key for generation {gen}")
        return cipher.encrypt(self._keys[gen], plaintext, key_gen=gen, aad=aad)

    def decrypt(self, blob: bytes, *, aad: bytes = b"") -> bytes:
        gen = cipher.key_gen_of(blob)
        key = self._keys.get(gen)
        if key is None:
            raise CipherError(f"no key for generation {gen}")
        return cipher.decrypt(key=key, blob=blob, aad=aad)
