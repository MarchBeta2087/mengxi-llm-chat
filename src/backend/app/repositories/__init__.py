"""仓储层：封装 SQLAlchemy 查询，业务层不直接拼 SQL。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import ApiKey
from app.models.recovery import AuditLog
from app.models.user import User, UserGroup


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_username(self, username: str) -> User | None:
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[User]:
        result = await self.session.execute(
            select(User).order_by(User.created_at).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def add(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        return user


class GroupRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, group_id: uuid.UUID) -> UserGroup | None:
        return await self.session.get(UserGroup, group_id)

    async def get_by_name(self, name: str) -> UserGroup | None:
        result = await self.session.execute(select(UserGroup).where(UserGroup.name == name))
        return result.scalar_one_or_none()

    async def list(self) -> list[UserGroup]:
        result = await self.session.execute(select(UserGroup).order_by(UserGroup.name))
        return list(result.scalars().all())

    async def add(self, group: UserGroup) -> UserGroup:
        self.session.add(group)
        await self.session.flush()
        return group


class ApiKeyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, key_id: uuid.UUID) -> ApiKey | None:
        return await self.session.get(ApiKey, key_id)

    async def list_private_for_user(self, user_id: uuid.UUID) -> list[ApiKey]:
        result = await self.session.execute(
            select(ApiKey).where(ApiKey.user_id == user_id).order_by(ApiKey.created_at)
        )
        return list(result.scalars().all())

    async def list_public(self) -> list[ApiKey]:
        result = await self.session.execute(
            select(ApiKey).where(ApiKey.user_id.is_(None)).order_by(ApiKey.created_at)
        )
        return list(result.scalars().all())

    async def add(self, api_key: ApiKey) -> ApiKey:
        self.session.add(api_key)
        await self.session.flush()
        return api_key

    async def delete(self, api_key: ApiKey) -> None:
        await self.session.delete(api_key)


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, log: AuditLog) -> AuditLog:
        self.session.add(log)
        await self.session.flush()
        return log

    async def list_for_user(
        self, user_id: uuid.UUID, *, limit: int = 100, offset: int = 0
    ) -> list[AuditLog]:
        result = await self.session.execute(
            select(AuditLog)
            .where(AuditLog.user_id == user_id)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def list_all(
        self,
        *,
        user_id: uuid.UUID | None = None,
        key_id: uuid.UUID | None = None,
        status: int | None = None,
        fallback_only: bool = False,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLog]:
        stmt = select(AuditLog)
        if user_id is not None:
            stmt = stmt.where(AuditLog.user_id == user_id)
        if key_id is not None:
            stmt = stmt.where(AuditLog.key_id == key_id)
        if status is not None:
            stmt = stmt.where(AuditLog.status == status)
        if fallback_only:
            stmt = stmt.where(AuditLog.fallback_to_public.is_(True))
        if start is not None:
            stmt = stmt.where(AuditLog.created_at >= start)
        if end is not None:
            stmt = stmt.where(AuditLog.created_at <= end)
        stmt = (
            stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
