"""管理后台路由：主密钥、用户/用户组、配额、审计检索。"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_admin
from app.core.errors import BadRequest, NotFound
from app.repositories import AuditRepository, GroupRepository, UserRepository
from app.schemas.admin import (
    AuditRead,
    GroupCreate,
    GroupRead,
    GroupUpdate,
    UserAdminRead,
    UserAdminUpdate,
)
from app.schemas.common import PassphraseRequest
from app.schemas.recovery import RecoveryUseRequest
from app.services.recovery import RecoveryService

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _provider(request: Request):
    provider = request.app.state.kek_provider
    if provider is None:
        raise BadRequest("主密钥提供者未就绪")
    return provider


def _ok(data, message: str = "ok") -> dict:
    return {"code": 0, "data": data, "message": message}


def _recovery_service(request: Request, session: AsyncSession) -> RecoveryService:
    return RecoveryService(
        session,
        request.app.state.kek_provider,
        request.app.state.key_manager,
        request.app.state.settings,
        cache=request.app.state.conversation_cache,
    )


# --- 主密钥 ---
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
    return _ok(provider.status())


@router.post("/kek/initialize")
async def kek_initialize(body: PassphraseRequest, request: Request) -> dict:
    provider = _provider(request)
    await provider.initialize(body.passphrase)
    request.app.state.key_manager.reset()
    codes: list[str] = []
    if request.app.state.kek_provider is not None:
        # 初始化即生成恢复码，明文仅此一次返回
        async with request.app.state.db.session() as session:
            codes = await _recovery_service(request, session).generate()
    status = provider.status()
    status["recovery_codes"] = codes
    return _ok(status)


@router.post("/kek/unlock")
async def kek_unlock(body: PassphraseRequest, request: Request) -> dict:
    provider = _provider(request)
    await provider.unlock(body.passphrase)
    request.app.state.key_manager.reset()
    return _ok(provider.status())


@router.post("/kek/lock")
async def kek_lock(request: Request) -> dict:
    provider = _provider(request)
    provider.lock()
    request.app.state.key_manager.reset()
    return _ok(provider.status())


# --- 恢复码 ---
@router.get("/recovery-codes")
async def recovery_status(
    request: Request,
    _: object = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    service = _recovery_service(request, session)
    return _ok({"remaining": await service.remaining()})


@router.post("/recovery-codes/regenerate")
async def recovery_regenerate(
    request: Request,
    _: object = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    codes = await _recovery_service(request, session).generate()
    return _ok({"codes": codes})


@router.post("/recovery-codes/use")
async def recovery_use(
    body: RecoveryUseRequest,
    request: Request,
    _: object = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    codes = await _recovery_service(request, session).use(
        body.code, new_passphrase=body.new_passphrase
    )
    return _ok({"codes": codes})


# --- 用户管理 ---
@router.get("/users")
async def list_users(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: object = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    users = await UserRepository(session).list(limit=limit, offset=offset)
    data = [UserAdminRead.model_validate(u).model_dump(mode="json") for u in users]
    return _ok(data)


@router.patch("/users/{user_id}")
async def update_user(
    user_id: uuid.UUID,
    body: UserAdminUpdate,
    _: object = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    repo = UserRepository(session)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise NotFound("用户不存在")

    if body.daily_quota_tokens is not None:
        user.daily_quota_tokens = body.daily_quota_tokens
    if body.status is not None:
        user.status = body.status.value
    if body.role is not None:
        user.role = body.role.value
    if "group_id" in body.model_fields_set:
        if body.group_id is not None:
            group = await GroupRepository(session).get(body.group_id)
            if group is None:
                raise BadRequest("用户组不存在")
        user.group_id = body.group_id

    await session.commit()
    return _ok(UserAdminRead.model_validate(user).model_dump(mode="json"))


# --- 用户组管理 ---
@router.get("/groups")
async def list_groups(
    _: object = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    groups = await GroupRepository(session).list()
    data = [GroupRead.model_validate(g).model_dump(mode="json") for g in groups]
    return _ok(data)


@router.post("/groups", status_code=201)
async def create_group(
    body: GroupCreate,
    _: object = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    repo = GroupRepository(session)
    if await repo.get_by_name(body.name) is not None:
        raise BadRequest("用户组已存在")
    from app.models.user import UserGroup

    group = await repo.add(UserGroup(name=body.name, daily_quota_tokens=body.daily_quota_tokens))
    await session.commit()
    return _ok(GroupRead.model_validate(group).model_dump(mode="json"))


@router.patch("/groups/{group_id}")
async def update_group(
    group_id: uuid.UUID,
    body: GroupUpdate,
    _: object = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    repo = GroupRepository(session)
    group = await repo.get(group_id)
    if group is None:
        raise NotFound("用户组不存在")
    if body.name is not None:
        group.name = body.name
    if body.daily_quota_tokens is not None:
        group.daily_quota_tokens = body.daily_quota_tokens
    await session.commit()
    return _ok(GroupRead.model_validate(group).model_dump(mode="json"))


# --- 审计检索 ---
@router.get("/audit")
async def query_audit(
    user_id: uuid.UUID | None = Query(default=None),
    key_id: uuid.UUID | None = Query(default=None),
    status: int | None = Query(default=None),
    fallback_only: bool = Query(default=False),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: object = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    logs = await AuditRepository(session).list_all(
        user_id=user_id,
        key_id=key_id,
        status=status,
        fallback_only=fallback_only,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
    )
    data = [AuditRead.model_validate(log).model_dump(mode="json") for log in logs]
    return _ok(data)


_AUDIT_EXPORT_HEADERS = [
    "id",
    "created_at",
    "user_id",
    "key_id",
    "key_type",
    "model",
    "base_url_host",
    "tokens_in",
    "tokens_out",
    "latency_ms",
    "status",
    "fallback_to_public",
    "client_ip",
]


@router.get("/audit/export")
async def export_audit(
    user_id: uuid.UUID | None = Query(default=None),
    key_id: uuid.UUID | None = Query(default=None),
    status: int | None = Query(default=None),
    fallback_only: bool = Query(default=False),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    _: object = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """审计导出 CSV（最多 10000 行，应用与检索相同的过滤条件）。"""
    logs = await AuditRepository(session).list_all(
        user_id=user_id,
        key_id=key_id,
        status=status,
        fallback_only=fallback_only,
        start=start,
        end=end,
        limit=10000,
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_AUDIT_EXPORT_HEADERS)
    for log in logs:
        writer.writerow(
            [
                log.id,
                log.created_at,
                log.user_id,
                log.key_id,
                log.key_type,
                log.model,
                log.base_url_host,
                log.tokens_in,
                log.tokens_out,
                log.latency_ms,
                log.status,
                log.fallback_to_public,
                log.client_ip,
            ]
        )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="audit.csv"'},
    )
