"""安全工具测试：脱敏与日志过滤。"""

from __future__ import annotations

import logging

from app.core.security import SensitiveDataFilter, mask_key, redact


def test_mask_key_never_leaks_full_key() -> None:
    assert mask_key("sk-abcdefghijklmnop") == "sk-...mnop"
    assert mask_key("") == ""


def test_redact_removes_secrets() -> None:
    text = "token sk-abcdef123456 and Bearer abcdefghijkl"
    out = redact(text)
    assert "sk-abcdef123456" not in out
    assert "abcdefghijkl" not in out
    assert "***REDACTED***" in out


def test_sensitive_filter_scrubs_log_record() -> None:
    record = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="key=%s",
        args=("sk-secretsecretsecret",),
        exc_info=None,
    )
    SensitiveDataFilter().filter(record)
    rendered = record.getMessage()
    assert "sk-secretsecretsecret" not in rendered
