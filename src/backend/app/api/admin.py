"""管理后台路由（M1：主密钥状态与解锁）。"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.errors import BadRequest
from app.schemas.common import PassphraseRequest

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _provider(request: Request):
    provider = request.app.state.kek_provider
    if provider is None:
        raise BadRequest("主密钥提供者未就绪")
    return provider


@router.get("/kek")
async def kek_status(request: Request) -> dict:
    provider = request.app.state.kek_provider
    if provider is None:
        return {
            "code": 50001,
            "data": {
                "profile": request.app.state.settings.kek_profile,
                "state": "unconfigured",
            },
            "message": "主密钥提供者未就绪",
        }
    return {"code": 0, "data": provider.status(), "message": "ok"}


@router.post("/kek/initialize")
async def kek_initialize(body: PassphraseRequest, request: Request) -> dict:
    provider = _provider(request)
    await provider.initialize(body.passphrase)
    request.app.state.key_manager.reset()
    return {"code": 0, "data": provider.status(), "message": "ok"}


@router.post("/kek/unlock")
async def kek_unlock(body: PassphraseRequest, request: Request) -> dict:
    provider = _provider(request)
    await provider.unlock(body.passphrase)
    request.app.state.key_manager.reset()
    return {"code": 0, "data": provider.status(), "message": "ok"}


@router.post("/kek/lock")
async def kek_lock(request: Request) -> dict:
    provider = _provider(request)
    provider.lock()
    request.app.state.key_manager.reset()
    return {"code": 0, "data": provider.status(), "message": "ok"}
