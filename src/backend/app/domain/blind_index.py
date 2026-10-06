"""盲索引：密文无法 LIKE，用 HMAC 指纹建立可搜索映射（见设计说明书 §7.4）。

- 分词：英文/数字按词（长度 < 2 丢弃），中文按 2-gram；
- 指纹：``HMAC-SHA256(index_key, token)``，不可逆，不含明文；
- ``index_key`` 由主密钥经 HKDF 派生，与数据分离。
"""

from __future__ import annotations

import hashlib
import hmac
import re

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

MIN_TOKEN_LEN = 2
_WORD_RE = re.compile(r"[A-Za-z0-9_]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_HKDF_INFO = b"mengxi-blind-index"


def derive_index_key(secret: bytes) -> bytes:
    """由主密钥派生盲索引密钥。"""
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_HKDF_INFO).derive(secret)


def tokenize(text: str) -> set[str]:
    """生成检索 token 集合（英文词 + 中文 2-gram）。"""
    tokens: set[str] = set()
    for word in _WORD_RE.findall(text or ""):
        lowered = word.lower()
        if len(lowered) >= MIN_TOKEN_LEN:
            tokens.add(lowered)
    for run in _CJK_RE.findall(text or ""):
        if len(run) < MIN_TOKEN_LEN:
            continue
        for index in range(len(run) - MIN_TOKEN_LEN + 1):
            tokens.add(run[index : index + MIN_TOKEN_LEN])
    return tokens


def fingerprint(index_key: bytes, token: str) -> bytes:
    return hmac.new(index_key, token.encode("utf-8"), hashlib.sha256).digest()


def fingerprints(index_key: bytes, text: str) -> set[bytes]:
    return {fingerprint(index_key, token) for token in tokenize(text)}
