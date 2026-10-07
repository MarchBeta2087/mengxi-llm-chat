"""仓储层：封装 SQLAlchemy 查询，业务层不直接拼 SQL。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import ApiKey
from app.models.conversation import Conversation, Message, MessageKeyword
from app.models.plugin import GroupPlugin, Plugin, UserPlugin
from app.models.recovery import AuditLog, RecoveryCode
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

    async def usage_by_key(
        self, key_ids: list[uuid.UUID], *, user_id: uuid.UUID | None = None
    ) -> dict[uuid.UUID, dict]:
        """按 Key 聚合调用次数与 tokens（可限定某个用户，用于个人用量）。"""
        if not key_ids:
            return {}
        stmt = (
            select(
                AuditLog.key_id,
                func.count(),
                func.coalesce(func.sum(AuditLog.tokens_in), 0),
                func.coalesce(func.sum(AuditLog.tokens_out), 0),
            )
            .where(AuditLog.key_id.in_(key_ids))
            .group_by(AuditLog.key_id)
        )
        if user_id is not None:
            stmt = stmt.where(AuditLog.user_id == user_id)
        result = await self.session.execute(stmt)
        return {
            row[0]: {
                "calls": int(row[1]),
                "tokens_in": int(row[2]),
                "tokens_out": int(row[3]),
            }
            for row in result.all()
        }


class PluginRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, plugin_id: uuid.UUID) -> Plugin | None:
        return await self.session.get(Plugin, plugin_id)

    async def get_by_name(self, name: str) -> Plugin | None:
        result = await self.session.execute(select(Plugin).where(Plugin.name == name))
        return result.scalar_one_or_none()

    async def list(self, *, status: str | None = None) -> list[Plugin]:
        stmt = select(Plugin).order_by(Plugin.name)
        if status is not None:
            stmt = stmt.where(Plugin.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def add(self, plugin: Plugin) -> Plugin:
        self.session.add(plugin)
        await self.session.flush()
        return plugin

    async def delete(self, plugin: Plugin) -> None:
        await self.session.delete(plugin)


class UserPluginRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: uuid.UUID, plugin_id: uuid.UUID) -> UserPlugin | None:
        return await self.session.get(UserPlugin, (user_id, plugin_id))

    async def map_for_user(self, user_id: uuid.UUID) -> dict[uuid.UUID, bool]:
        result = await self.session.execute(select(UserPlugin).where(UserPlugin.user_id == user_id))
        return {row.plugin_id: row.enabled for row in result.scalars().all()}

    async def set(self, user_id: uuid.UUID, plugin_id: uuid.UUID, enabled: bool) -> UserPlugin:
        row = await self.get(user_id, plugin_id)
        if row is None:
            row = UserPlugin(user_id=user_id, plugin_id=plugin_id, enabled=enabled)
            self.session.add(row)
        else:
            row.enabled = enabled
        await self.session.flush()
        return row


class GroupPluginRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, group_id: uuid.UUID, plugin_id: uuid.UUID) -> GroupPlugin | None:
        return await self.session.get(GroupPlugin, (group_id, plugin_id))

    async def map_for_group(self, group_id: uuid.UUID) -> dict[uuid.UUID, str]:
        result = await self.session.execute(
            select(GroupPlugin).where(GroupPlugin.group_id == group_id)
        )
        return {row.plugin_id: row.state for row in result.scalars().all()}

    async def set(self, group_id: uuid.UUID, plugin_id: uuid.UUID, state: str) -> GroupPlugin:
        row = await self.get(group_id, plugin_id)
        if row is None:
            row = GroupPlugin(group_id=group_id, plugin_id=plugin_id, state=state)
            self.session.add(row)
        else:
            row.state = state
        await self.session.flush()
        return row

    async def delete(self, group_id: uuid.UUID, plugin_id: uuid.UUID) -> None:
        row = await self.get(group_id, plugin_id)
        if row is not None:
            await self.session.delete(row)


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, conversation_id: uuid.UUID) -> Conversation | None:
        return await self.session.get(Conversation, conversation_id)

    async def list_for_user(
        self, user_id: uuid.UUID, *, include_archived: bool = False
    ) -> list[Conversation]:
        stmt = select(Conversation).where(Conversation.user_id == user_id)
        if not include_archived:
            stmt = stmt.where(Conversation.archived.is_(False))
        stmt = stmt.order_by(Conversation.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def search_titles(
        self, user_id: uuid.UUID, query: str, *, limit: int = 20
    ) -> list[Conversation]:
        stmt = (
            select(Conversation)
            .where(Conversation.user_id == user_id, Conversation.title.ilike(f"%{query}%"))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def add(self, conversation: Conversation) -> Conversation:
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def delete(self, conversation: Conversation) -> None:
        await self.session.delete(conversation)


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, message: Message) -> Message:
        self.session.add(message)
        await self.session.flush()
        return message

    async def list_for_conversation(
        self, conversation_id: uuid.UUID, *, limit: int = 200
    ) -> list[Message]:
        result = await self.session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at, Message.id)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def recent_for_conversation(
        self, conversation_id: uuid.UUID, *, limit: int = 40
    ) -> list[Message]:
        result = await self.session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
        )
        rows = list(result.scalars().all())
        rows.reverse()
        return rows

    async def list_by_ids(self, message_ids: list[uuid.UUID]) -> list[Message]:
        if not message_ids:
            return []
        result = await self.session.execute(select(Message).where(Message.id.in_(message_ids)))
        return list(result.scalars().all())


class MessageKeywordRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_many(self, message_id: uuid.UUID, fingerprints: set[bytes]) -> None:
        for fp in fingerprints:
            self.session.add(MessageKeyword(message_id=message_id, keyword_fp=fp))
        await self.session.flush()

    async def search(self, fingerprints: set[bytes], *, limit: int = 200) -> list[uuid.UUID]:
        if not fingerprints:
            return []
        result = await self.session.execute(
            select(MessageKeyword.message_id)
            .where(MessageKeyword.keyword_fp.in_(list(fingerprints)))
            .limit(limit)
        )
        return list(dict.fromkeys(result.scalars().all()))


class RecoveryCodeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, row: RecoveryCode) -> RecoveryCode:
        self.session.add(row)
        await self.session.flush()
        return row

    async def get_by_hash(self, code_hash: bytes) -> RecoveryCode | None:
        result = await self.session.execute(
            select(RecoveryCode).where(RecoveryCode.code_hash == code_hash)
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[RecoveryCode]:
        result = await self.session.execute(select(RecoveryCode).order_by(RecoveryCode.created_at))
        return list(result.scalars().all())

    async def delete_all(self) -> None:
        await self.session.execute(delete(RecoveryCode))
        await self.session.flush()

    async def count_unused(self) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(RecoveryCode).where(RecoveryCode.used_at.is_(None))
        )
        return int(result.scalar_one())
