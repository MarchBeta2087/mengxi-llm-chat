"""会话服务：透明加解密、盲索引检索、DEK_conv 缓存（见设计说明书 §7.3/§7.4）。

- 消息正文以 AES-256-GCM 加密后 Base64 落库，密钥为该用户的 DEK_conv；
- DEK_conv 解密后进入带 TTL 的进程内缓存，避免逐条解密钥；
- 盲索引用于加密会话的全文检索（默认按配置开关）。
"""

from __future__ import annotations

import base64
import uuid
from dataclasses import dataclass

from cachetools import TTLCache
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import cipher
from app.core.errors import Forbidden, KekLocked, NotFound
from app.domain.blind_index import derive_index_key, fingerprints
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.repositories import (
    ConversationRepository,
    MessageKeywordRepository,
    MessageRepository,
)
from app.services.key_manager import KeyManager

DEFAULT_CONTEXT_LIMIT = 40
FIRST_TURN_TITLE_LEN = 30


class ConversationKeyCache:
    """DEK_conv 进程内 LRU+TTL 缓存。"""

    def __init__(self, *, ttl_seconds: int = 900, maxsize: int = 10_000) -> None:
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl_seconds)

    def get(self, user_id: uuid.UUID) -> bytes | None:
        return self._cache.get(user_id)

    def put(self, user_id: uuid.UUID, dek: bytes) -> None:
        self._cache[user_id] = dek

    def invalidate(self, user_id: uuid.UUID) -> None:
        self._cache.pop(user_id, None)

    def clear(self) -> None:
        self._cache.clear()


@dataclass
class ContextMessage:
    role: str
    content: str


class ConversationService:
    def __init__(
        self,
        session: AsyncSession,
        key_manager: KeyManager,
        cache: ConversationKeyCache,
        *,
        search_enabled: bool = False,
    ) -> None:
        self.session = session
        self.key_manager = key_manager
        self.cache = cache
        self.search_enabled = search_enabled
        self.conversation_repo = ConversationRepository(session)
        self.message_repo = MessageRepository(session)
        self.keyword_repo = MessageKeywordRepository(session)

    # --- 密钥 ---
    async def conversation_key(self, user: User) -> bytes:
        cached = self.cache.get(user.id)
        if cached is not None:
            return cached
        if user.conversation_key_encrypted is None:
            dek, wrapped = self.key_manager.new_conversation_key()
            user.conversation_key_encrypted = wrapped
            await self.session.flush()
            await self.session.commit()
        else:
            dek = self.key_manager.unwrap_conversation_key(user.conversation_key_encrypted)
        self.cache.put(user.id, dek)
        return dek

    def index_key(self) -> bytes | None:
        if not self.search_enabled:
            return None
        try:
            return derive_index_key(self.key_manager.kek.kek)
        except KekLocked:
            return None

    # --- 会话 ---
    async def create(
        self, user: User, *, title: str = "新会话", model: str | None = None, encrypted: bool = True
    ) -> Conversation:
        conversation = Conversation(user_id=user.id, title=title, model=model, encrypted=encrypted)
        await self.conversation_repo.add(conversation)
        await self.session.commit()
        return conversation

    async def list(self, user: User, *, include_archived: bool = False) -> list[Conversation]:
        return await self.conversation_repo.list_for_user(
            user.id, include_archived=include_archived
        )

    async def get_owned(self, user: User, conversation_id: uuid.UUID) -> Conversation:
        conversation = await self.conversation_repo.get(conversation_id)
        if conversation is None:
            raise NotFound("会话不存在")
        if conversation.user_id != user.id:
            raise Forbidden("无权访问他人会话")
        return conversation

    async def rename(self, user: User, conversation_id: uuid.UUID, title: str) -> Conversation:
        conversation = await self.get_owned(user, conversation_id)
        conversation.title = title
        await self.session.commit()
        return conversation

    async def set_archived(
        self, user: User, conversation_id: uuid.UUID, archived: bool
    ) -> Conversation:
        conversation = await self.get_owned(user, conversation_id)
        conversation.archived = archived
        await self.session.commit()
        return conversation

    async def delete(self, user: User, conversation_id: uuid.UUID) -> None:
        conversation = await self.get_owned(user, conversation_id)
        await self.conversation_repo.delete(conversation)
        await self.session.commit()

    # --- 消息 ---
    def _encrypt(self, dek: bytes, conversation_id: uuid.UUID, content: str) -> str:
        blob = cipher.encrypt(
            dek, content.encode("utf-8"), key_gen=0, aad=f"msg:{conversation_id}".encode()
        )
        return base64.b64encode(blob).decode("ascii")

    def _decrypt(self, dek: bytes, conversation_id: uuid.UUID, payload: str) -> str:
        blob = base64.b64decode(payload.encode("ascii"))
        return cipher.decrypt(key=dek, blob=blob, aad=f"msg:{conversation_id}".encode()).decode(
            "utf-8"
        )

    async def append_message(
        self,
        user: User,
        conversation: Conversation,
        role: str,
        content: str,
        *,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> Message:
        dek = await self.conversation_key(user)
        message = Message(
            conversation_id=conversation.id,
            role=role,
            content_encrypted=self._encrypt(dek, conversation.id, content),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
        await self.message_repo.add(message)

        index_key = self.index_key()
        if index_key is not None and conversation.encrypted:
            await self.keyword_repo.add_many(message.id, fingerprints(index_key, content))

        if role == "user" and conversation.title == "新会话":
            conversation.title = content[:FIRST_TURN_TITLE_LEN] or "新会话"
        await self.session.commit()
        return message

    async def messages(self, user: User, conversation: Conversation) -> list[tuple[Message, str]]:
        dek = await self.conversation_key(user)
        rows = await self.message_repo.list_for_conversation(conversation.id)
        return [(row, self._decrypt(dek, conversation.id, row.content_encrypted)) for row in rows]

    async def context(
        self, user: User, conversation: Conversation, *, limit: int = DEFAULT_CONTEXT_LIMIT
    ) -> list[ContextMessage]:
        dek = await self.conversation_key(user)
        rows = await self.message_repo.recent_for_conversation(conversation.id, limit=limit)
        return [
            ContextMessage(
                role=row.role, content=self._decrypt(dek, conversation.id, row.content_encrypted)
            )
            for row in rows
            if row.role in ("user", "assistant", "system")
        ]

    # --- 搜索 ---
    async def search(self, user: User, query: str, *, limit: int = 20) -> list[dict]:
        """标题匹配 + （可选）加密会话盲索引匹配。"""
        results: list[dict] = []
        seen: set[str] = set()

        for conversation in await self.conversation_repo.search_titles(user.id, query, limit=limit):
            key = f"title:{conversation.id}"
            seen.add(key)
            results.append(
                {
                    "conversation_id": str(conversation.id),
                    "title": conversation.title,
                    "kind": "title",
                    "message_id": None,
                    "snippet": None,
                }
            )

        index_key = self.index_key()
        if index_key is not None and query.strip():
            fps = fingerprints(index_key, query)
            message_ids = await self.keyword_repo.search(fps, limit=limit * 5)
            rows = await self.message_repo.list_by_ids(message_ids)
            dek = await self.conversation_key(user)
            for row in rows:
                conversation = await self.conversation_repo.get(row.conversation_id)
                if conversation is None or conversation.user_id != user.id:
                    continue
                key = f"msg:{row.id}"
                if key in seen:
                    continue
                seen.add(key)
                text = self._decrypt(dek, conversation.id, row.content_encrypted)
                results.append(
                    {
                        "conversation_id": str(conversation.id),
                        "title": conversation.title,
                        "kind": "message",
                        "message_id": str(row.id),
                        "snippet": text[:120],
                    }
                )
                if len(results) >= limit:
                    break

        return results[:limit]
