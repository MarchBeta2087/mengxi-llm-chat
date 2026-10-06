"""恢复码机制测试。"""

from __future__ import annotations

import os

import pytest

from app.core.crypto.kek import Argon2Params
from app.core.crypto.recovery import (
    DEFAULT_CODE_COUNT,
    code_hash,
    generate_code,
    generate_recovery_codes,
    normalize_code,
    recover_kek,
)
from app.core.errors import CipherError

FAST = Argon2Params(time_cost=1, memory_cost=8192, parallelism=1, hash_len=32)
SECRET = os.urandom(32)


def test_generate_code_format() -> None:
    code = generate_code()
    assert len(code) == 14
    assert code.count("-") == 2
    assert all(len(group) == 4 for group in code.split("-"))


def test_codes_are_unique() -> None:
    codes = {generate_code() for _ in range(200)}
    assert len(codes) == 200


def test_generate_and_recover() -> None:
    kek = os.urandom(32)
    generated = generate_recovery_codes(kek, SECRET, FAST)
    assert len(generated.plaintext) == DEFAULT_CODE_COUNT
    assert len(generated.records) == DEFAULT_CODE_COUNT

    for code, record in zip(generated.plaintext, generated.records, strict=True):
        assert record.code_hash == code_hash(SECRET, code)
        assert recover_kek(code, record, FAST) == kek


def test_recovery_is_whitespace_insensitive() -> None:
    kek = os.urandom(32)
    generated = generate_recovery_codes(kek, SECRET, FAST, count=1)
    code = generated.plaintext[0]
    messy = f" {code.lower()} "
    assert recover_kek(messy, generated.records[0], FAST) == kek


def test_wrong_code_fails() -> None:
    kek = os.urandom(32)
    generated = generate_recovery_codes(kek, SECRET, FAST, count=1)
    wrong = generate_code()
    while normalize_code(wrong) == normalize_code(generated.plaintext[0]):
        wrong = generate_code()
    with pytest.raises(CipherError):
        recover_kek(wrong, generated.records[0], FAST)
