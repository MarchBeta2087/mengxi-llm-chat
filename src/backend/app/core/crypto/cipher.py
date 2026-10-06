"""密文封装：AES-256-GCM + 两字节结构化头（见设计说明书 §3.1）。

    cipher_blob = alg(1B) || key_gen(1B) || iv(12B) || ciphertext(N) || tag(16B)

- ``alg``     算法标识（0x01 = AES-256-GCM），为算法迁移预留。
- ``key_gen`` 密钥代次，解密方据此直接选钥，无需试错。
- ``iv``      每条记录独立随机，严禁复用。
- 头两字节一并计入 AAD，防止篡改代次诱导错误选钥。
"""

from __future__ import annotations

import os
import struct

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.errors import CipherError

ALG_AES_256_GCM = 0x01
SUPPORTED_ALGS: frozenset[int] = frozenset({ALG_AES_256_GCM})

KEY_LEN = 32
IV_LEN = 12
TAG_LEN = 16
HEADER_LEN = 2
MIN_BLOB_LEN = HEADER_LEN + IV_LEN + TAG_LEN

_HEADER = struct.Struct(">BB")
_MAX_KEY_GEN = 0xFF


def _check_key(key: bytes) -> None:
    if len(key) != KEY_LEN:
        raise ValueError(f"AES-256 key must be {KEY_LEN} bytes, got {len(key)}")


def build_aad(header: bytes, context: bytes = b"") -> bytes:
    """AAD = 头字节 + 记录上下文，绑定密文与元数据。"""
    return header + b"|" + context


def peek_header(blob: bytes) -> tuple[int, int]:
    """返回 (alg, key_gen)，不解密。"""
    if len(blob) < HEADER_LEN:
        raise CipherError("cipher blob too short to contain header")
    alg, key_gen = _HEADER.unpack_from(blob, 0)
    return alg, key_gen


def key_gen_of(blob: bytes) -> int:
    return peek_header(blob)[1]


def encrypt(
    key: bytes,
    plaintext: bytes,
    *,
    key_gen: int = 0,
    aad: bytes = b"",
    alg: int = ALG_AES_256_GCM,
) -> bytes:
    """加密并返回完整密文封装。"""
    _check_key(key)
    if alg not in SUPPORTED_ALGS:
        raise ValueError(f"unsupported algorithm id: 0x{alg:02x}")
    if not 0 <= key_gen <= _MAX_KEY_GEN:
        raise ValueError(f"key_gen out of range [0, {_MAX_KEY_GEN}]: {key_gen}")

    header = _HEADER.pack(alg, key_gen)
    nonce = os.urandom(IV_LEN)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, build_aad(header, aad))
    return header + nonce + ciphertext


def decrypt(*, key: bytes, blob: bytes, aad: bytes = b"") -> bytes:
    """校验并解密。调用方须已按 ``key_gen_of(blob)`` 选好 ``key``。"""
    _check_key(key)
    if len(blob) < MIN_BLOB_LEN:
        raise CipherError("cipher blob too short")

    alg, _key_gen = peek_header(blob)
    if alg not in SUPPORTED_ALGS:
        raise CipherError(f"unsupported algorithm id: 0x{alg:02x}")

    header = blob[:HEADER_LEN]
    nonce = blob[HEADER_LEN : HEADER_LEN + IV_LEN]
    ciphertext = blob[HEADER_LEN + IV_LEN :]
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, build_aad(header, aad))
    except InvalidTag as exc:
        raise CipherError("ciphertext authentication failed") from exc
