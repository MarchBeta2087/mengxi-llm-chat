"""恢复码机制（见设计说明书 §3.4）。

- 每个恢复码的恢复密钥 rk = Argon2id(code, salt)；
- 用 rk 加密 KEK 副本入库；code_hash = HMAC-SHA256(secret, code) 作为索引；
- 明文恢复码仅在生成时返回一次，服务端不落盘、不写日志。
"""

from __future__ import annotations

import hmac
import os
import secrets
from dataclasses import dataclass, field

from app.core.crypto import cipher
from app.core.crypto.kek import Argon2Params

# 去掉 I/O/0/1 等易混字符，共 32 个字符
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_GROUP_LEN = 4
CODE_GROUPS = 3
DEFAULT_CODE_COUNT = 8
RECOVERY_AAD = b"recovery-code"


def _random_group() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_GROUP_LEN))


def generate_code() -> str:
    """生成 XXXX-XXXX-XXXX 格式的一次性恢复码。"""
    return "-".join(_random_group() for _ in range(CODE_GROUPS))


def normalize_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


def code_hash(hmac_secret: bytes, code: str) -> bytes:
    return hmac.new(hmac_secret, normalize_code(code).encode("ascii"), "sha256").digest()


def derive_recovery_key(code: str, salt: bytes, params: Argon2Params) -> bytes:
    return params.derive(normalize_code(code), salt)


@dataclass(frozen=True)
class RecoveryCodeRecord:
    """入库结构（对应 recovery_codes 表）。"""

    code_hash: bytes
    salt: bytes
    kek_wrapped: bytes


@dataclass
class GeneratedRecoveryCodes:
    records: list[RecoveryCodeRecord] = field(default_factory=list)
    plaintext: list[str] = field(default_factory=list)


def generate_recovery_codes(
    kek: bytes,
    hmac_secret: bytes,
    params: Argon2Params,
    *,
    count: int = DEFAULT_CODE_COUNT,
) -> GeneratedRecoveryCodes:
    """生成一批恢复码，返回入库记录与仅展示一次的明文码。"""
    result = GeneratedRecoveryCodes()
    for _ in range(count):
        code = generate_code()
        salt = os.urandom(params.salt_len)
        rk = derive_recovery_key(code, salt, params)
        wrapped = cipher.encrypt(rk, kek, key_gen=0, aad=RECOVERY_AAD)
        result.records.append(RecoveryCodeRecord(code_hash(hmac_secret, code), salt, wrapped))
        result.plaintext.append(code)
    return result


def recover_kek(code: str, record: RecoveryCodeRecord, params: Argon2Params) -> bytes:
    """用恢复码解出 KEK 副本；恢复码错误将因认证失败抛 CipherError。"""
    rk = derive_recovery_key(code, record.salt, params)
    return cipher.decrypt(key=rk, blob=record.kek_wrapped, aad=RECOVERY_AAD)
