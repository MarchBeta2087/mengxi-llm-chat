"""密钥路由（见设计说明书 §9.2）。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_key_manager,
    get_session,
    get_ssrf_policy,
)
from app.core.ssrf import SsrfPolicy
from app.models.enums import KeyStatus
from app.models.user import User
from app.schemas.keys import AvailableKeyRead, KeyCreate, KeyUpdate
from app.services.key_manager import KeyManager
from app.services.keys import KeysService, key_to_read

router = APIRouter(prefix="/api/keys", tags=["keys"])


def _service(session: AsyncSession, key_manager: KeyManager, policy: SsrfPolicy) -> KeysService:
    return KeysService(session, key_manager, policy)


@router.get("")
async def list_keys(
    pool: str | None = Query(default=None, pattern="^(public|private)$"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    key_manager: KeyManager = Depends(get_key_manager),
    policy: SsrfPolicy = Depends(get_ssrf_policy),
) -> dict:
    keys = await _service(session, key_manager, policy).list(user, pool=pool)
    return {
        "code": 0,
        "data": [key_to_read(k).model_dump(mode="json") for k in keys],
        "message": "ok",
    }


@router.post("", status_code=201)
async def create_key(
    body: KeyCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    key_manager: KeyManager = Depends(get_key_manager),
    policy: SsrfPolicy = Depends(get_ssrf_policy),
) -> dict:
    key = await _service(session, key_manager, policy).create(user, body)
    return {"code": 0, "data": key_to_read(key).model_dump(mode="json"), "message": "ok"}


@router.patch("/{key_id}")
async def update_key(
    key_id: uuid.UUID,
    body: KeyUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    key_manager: KeyManager = Depends(get_key_manager),
    policy: SsrfPolicy = Depends(get_ssrf_policy),
) -> dict:
    key = await _service(session, key_manager, policy).update(user, key_id, body)
    return {"code": 0, "data": key_to_read(key).model_dump(mode="json"), "message": "ok"}


@router.delete("/{key_id}")
async def delete_key(
    key_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    key_manager: KeyManager = Depends(get_key_manager),
    policy: SsrfPolicy = Depends(get_ssrf_policy),
) -> dict:
    await _service(session, key_manager, policy).delete(user, key_id)
    return {"code": 0, "data": None, "message": "ok"}


@router.post("/{key_id}/test")
async def test_key(
    key_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    key_manager: KeyManager = Depends(get_key_manager),
    policy: SsrfPolicy = Depends(get_ssrf_policy),
) -> dict:
    client_ip = request.client.host if request.client else None
    result = await _service(session, key_manager, policy).test_connectivity(
        user, key_id, client_ip=client_ip
    )
    return {
        "code": 0,
        "data": {
            "ok": result.ok,
            "status_code": result.status_code,
            "latency_ms": result.latency_ms,
            "error": result.error,
        },
        "message": "ok",
    }


@router.get("/models", include_in_schema=True)
async def list_models(
    pool: str | None = Query(default=None, pattern="^(public|private)$"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    key_manager: KeyManager = Depends(get_key_manager),
    policy: SsrfPolicy = Depends(get_ssrf_policy),
) -> dict:
    """由当前可用 Key 池推导的模型列表（去重）。

    - 未指定 pool：用户可用池（私有 + 公有，仅启用中）；
    - 指定 pool：仅该池且启用中。
    """
    service = _service(session, key_manager, policy)
    if pool is None:
        keys = await service.available_keys(user)
    else:
        keys = [
            key
            for key in await service.list(user, pool=pool)
            if key.status == KeyStatus.ACTIVE.value
        ]
    models: list[str] = []
    for key in keys:
        for model in key.models_json or []:
            if model not in models:
                models.append(model)
    return {"code": 0, "data": models, "message": "ok"}


@router.get("/available", include_in_schema=True)
async def list_available_keys(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    key_manager: KeyManager = Depends(get_key_manager),
    policy: SsrfPolicy = Depends(get_ssrf_policy),
) -> dict:
    """当前用户可用的 Key（私有 + 公有，脱敏，含用量），供模型选择弹窗使用。"""
    service = _service(session, key_manager, policy)
    items = await service.available_with_usage(user)
    data = [
        AvailableKeyRead(
            id=key.id,
            provider_name=key.provider_name,
            masked_key=key.key_fingerprint,
            models=list(key.models_json or []),
            pool=key.priority_pool,
            usage_scope=scope,
            last_used_at=key.last_used_at,
            usage=usage,
        ).model_dump(mode="json")
        for key, usage, scope in items
    ]
    return {"code": 0, "data": data, "message": "ok"}
