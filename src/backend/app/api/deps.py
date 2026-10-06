"""FastAPI 依赖：会话、鉴权、基础设施。"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Forbidden, KekLocked, Unauthorized
from app.core.ssrf import SsrfPolicy
from app.models.user import User
from app.repositories import UserRepository
from app.services.key_manager import KeyManager


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    db = request.app.state.db
    async with db.session() as session:
        yield session


def get_ssrf_policy(request: Request) -> SsrfPolicy:
    return request.app.state.ssrf_policy


def get_key_manager(request: Request) -> KeyManager:
    manager: KeyManager | None = request.app.state.key_manager
    if manager is None:
        raise KekLocked("主密钥服务不可用")
    return manager


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    uid = request.session.get("uid")
    if not uid:
        raise Unauthorized("未登录")
    try:
        user_id = uuid.UUID(str(uid))
    except ValueError as exc:
        raise Unauthorized("登录状态无效") from exc

    user = await UserRepository(session).get_by_id(user_id)
    if user is None or not user.is_active:
        raise Unauthorized("登录状态无效")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise Forbidden("需要管理员权限")
    return user
