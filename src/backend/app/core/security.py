"""安全工具：口令哈希、Key 脱敏、敏感信息日志过滤（见设计说明书 §4.2）。"""

from __future__ import annotations

import logging
import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()

# 匹配常见密钥形态，作为日志兜底脱敏
_SENSITIVE_RE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{6,}"
    r"|Bearer\s+[A-Za-z0-9._\-]{6,}"
    r"|eyJ[A-Za-z0-9._\-]{20,})"  # 形似 JWT
)

_REDACTED = "***REDACTED***"


def hash_password(password: str) -> str:
    """Argon2id 口令哈希。"""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def mask_key(raw: str, *, prefix: int = 3, suffix: int = 4) -> str:
    """脱敏展示：sk-...abcd。永不返回完整 Key。"""
    if not raw:
        return ""
    tail = raw[-suffix:] if len(raw) >= suffix else raw
    return f"{raw[:prefix]}...{tail}"


def redact(text: str) -> str:
    """将文本中的疑似密钥替换为掩码。"""
    return _SENSITIVE_RE.sub(_REDACTED, text)


class SensitiveDataFilter(logging.Filter):
    """日志过滤器：拦截疑似密钥明文（§4.2）。"""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: redact(v) if isinstance(v, str) else v for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(redact(a) if isinstance(a, str) else a for a in record.args)
        return True
