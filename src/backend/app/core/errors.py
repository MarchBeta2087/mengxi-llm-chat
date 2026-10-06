"""领域异常与统一错误码（见设计说明书 §9.6）。

错误码约定：
    400xx  参数类
    401xx  认证类
    403xx  授权类
    429xx  限流/配额类
    500xx  内部类
    502xx  上游类
    503xx  服务不可用类
"""

from __future__ import annotations

from typing import Any


class MengxiError(Exception):
    """所有业务异常的基类。"""

    http_status: int = 400
    code: int = 400

    def __init__(self, message: str = "", **extra: Any) -> None:
        super().__init__(message or self.__class__.__name__)
        self.message = message or self.__class__.__name__
        self.extra = extra

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "data": None,
        }
        payload.update(self.extra)
        return payload


# --- 参数 / 请求 ---
class BadRequest(MengxiError):
    http_status = 400
    code = 400


class SsrfRejected(MengxiError):
    http_status = 400
    code = 40010


class CipherError(MengxiError):
    http_status = 500
    code = 50001


# --- 认证 / 授权 ---
class Unauthorized(MengxiError):
    http_status = 401
    code = 401


class WrongPassphrase(MengxiError):
    http_status = 401
    code = 40101


class Forbidden(MengxiError):
    http_status = 403
    code = 403


class NotFound(MengxiError):
    http_status = 404
    code = 404


# --- 限流 / 配额 ---
class RateLimited(MengxiError):
    http_status = 429
    code = 42900


class QuotaExceeded(MengxiError):
    http_status = 429
    code = 42901


# --- 上游 / 服务 ---
class UpstreamError(MengxiError):
    http_status = 502
    code = 502


class KeyPoolExhausted(MengxiError):
    http_status = 503
    code = 503


class KekLocked(MengxiError):
    http_status = 503
    code = 50301
