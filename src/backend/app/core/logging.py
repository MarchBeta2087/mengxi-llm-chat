"""日志装配：统一格式 + 敏感信息过滤。"""

from __future__ import annotations

import logging
import sys

from app.core.config import Settings
from app.core.security import SensitiveDataFilter

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s %(message)s"


def setup_logging(settings: Settings | None = None) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT))
    handler.addFilter(SensitiveDataFilter())

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.DEBUG if (settings and settings.debug) else logging.INFO)

    # 降低第三方库噪声
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
