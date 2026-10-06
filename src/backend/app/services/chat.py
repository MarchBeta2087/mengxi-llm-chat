"""聊天服务：调度 + 限流 + 熔断 + 回退 + 审计 + SSE 事件编排。

M1 为无状态基础聊天（对话落库与加密在 M4）。见设计说明书 §4.2/§4.5/§7.1。
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from urllib.parse import urlsplit

from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import KeyPoolExhausted, QuotaExceeded, RateLimited, UpstreamError
from app.core.ssrf import SsrfPolicy
from app.domain.ratelimit import LimitDecision, QuotaDecision, RateLimitSpec
from app.infra.upstream import UpstreamChunk, UpstreamClient
from app.models.api_key import ApiKey
from app.models.conversation import Conversation
from app.models.recovery import AuditLog
from app.models.user import User
from app.repositories import ApiKeyRepository, AuditRepository, GroupRepository
from app.services.conversation import ConversationService
from app.services.key_manager import KeyManager
from app.services.ratelimit import CircuitBreaker, RateLimiter
from app.services.scheduler import SchedulerService


@dataclass
class ChatEvent:
    event: str
    data: dict


@dataclass
class ChatMessage:
    role: str
    content: str


class ChatService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        user: User,
        key_manager: KeyManager,
        rate_limiter: RateLimiter,
        circuit_breaker: CircuitBreaker,
        scheduler: SchedulerService,
        policy: SsrfPolicy,
        upstream: object | None = None,
        fallback_to_public: bool = True,
        max_attempts: int = 3,
        user_rate_spec: RateLimitSpec | None = None,
        ip_rate_spec: RateLimitSpec | None = None,
        client_ip: str | None = None,
        conversations: ConversationService | None = None,
    ) -> None:
        self.session = session
        self.user = user
        self.key_manager = key_manager
        self.rate_limiter = rate_limiter
        self.circuit_breaker = circuit_breaker
        self.scheduler = scheduler
        self.policy = policy
        self.upstream = upstream or UpstreamClient(policy)
        self.fallback_to_public = fallback_to_public
        self.max_attempts = max_attempts
        self.user_rate_spec = user_rate_spec
        self.ip_rate_spec = ip_rate_spec
        self.client_ip = client_ip
        self.conversations = conversations
        self.keys = ApiKeyRepository(session)
        self.groups = GroupRepository(session)
        self.audit = AuditRepository(session)

    # --- 三层兜底：用户→用户组→IP（Key 级在选 Key 后校验）---
    async def _safe(self, coro):  # noqa: ANN001 - 内部降级包装
        """Redis 不可用时降级：已登录用户放行，不因限流设施故障拒绝服务（风险 R4）。"""
        try:
            return await coro
        except RedisError:
            return None

    async def _enforce_limits(self) -> None:
        if self.user.daily_quota_tokens > 0:
            quota: QuotaDecision | None = await self._safe(
                self.rate_limiter.check_user_quota(str(self.user.id), self.user.daily_quota_tokens)
            )
            if quota is not None and not quota.allowed:
                raise QuotaExceeded(
                    "今日配额已用完",
                    dimension="quota",
                    used=quota.used,
                    limit=quota.limit,
                )

        if self.user.group_id is not None:
            group = await self.groups.get(self.user.group_id)
            if group is not None and group.daily_quota_tokens > 0:
                group_quota: QuotaDecision | None = await self._safe(
                    self.rate_limiter.check_group_quota(str(group.id), group.daily_quota_tokens)
                )
                if group_quota is not None and not group_quota.allowed:
                    raise QuotaExceeded(
                        "用户组配额已用完",
                        dimension="group_quota",
                        used=group_quota.used,
                        limit=group_quota.limit,
                    )

        if self.user_rate_spec is not None and not self.user_rate_spec.is_unlimited:
            decision: LimitDecision | None = await self._safe(
                self.rate_limiter.consume_user_request(str(self.user.id), self.user_rate_spec)
            )
            if decision is not None and not decision.allowed:
                raise RateLimited(
                    "用户级限流",
                    dimension=decision.dimension.value if decision.dimension else None,
                )

        if self.ip_rate_spec is not None and not self.ip_rate_spec.is_unlimited and self.client_ip:
            ip_decision = await self._safe(
                self.rate_limiter.consume_ip_request(self.client_ip, self.ip_rate_spec)
            )
            if ip_decision is not None and not ip_decision.allowed:
                raise RateLimited(
                    "IP 级限流",
                    dimension=ip_decision.dimension.value if ip_decision.dimension else None,
                )

    async def stream(
        self, *, model: str, messages: list[ChatMessage], conversation: Conversation | None = None
    ) -> AsyncIterator[ChatEvent]:
        await self._enforce_limits()

        # 持久化本轮输入；构造上游上下文（历史密文解密 + 本轮消息）
        history: list[ChatMessage] = []
        if conversation is not None and self.conversations is not None:
            context = await self.conversations.context(self.user, conversation)
            history = [ChatMessage(role=c.role, content=c.content) for c in context]
            for message in messages:
                await self.conversations.append_message(
                    self.user, conversation, message.role, message.content
                )
        payload_messages = [*history, *messages]

        private_keys = await self.keys.list_private_for_user(self.user.id)
        public_keys = await self.keys.list_public()

        tried: set[str] = set()
        last_error: Exception | None = None

        for _ in range(self.max_attempts):
            picked = await self.scheduler.pick(
                [k for k in private_keys if str(k.id) not in tried],
                [k for k in public_keys if str(k.id) not in tried],
                model=model,
                fallback=self.fallback_to_public,
            )
            if picked is None:
                break
            key = picked.key
            tried.add(str(key.id))
            spec = RateLimitSpec.from_mapping(key.rate_limits_json)

            decision = await self._safe(self.rate_limiter.consume_key_request(key.id, spec))
            if decision is not None and not decision.allowed:
                last_error = RateLimited(
                    "Key 触发限流",
                    dimension=decision.dimension.value if decision.dimension else None,
                )
                continue
            token_decision = await self._safe(self.rate_limiter.precheck_key_tokens(key.id, spec))
            if token_decision is not None and not token_decision.allowed:
                last_error = RateLimited("Key 令牌额度耗尽")
                continue

            secret = self.key_manager.decrypt_secret(
                key.encrypted_key, aad=f"api-key:{key.id}".encode()
            )
            started = time.perf_counter()
            stream = self.upstream.stream_chat(
                base_url=key.base_url,
                api_key=secret,
                payload=self._payload(model, payload_messages),
            )

            # 连接阶段错误可在产出任何事件前回退到下一个 Key
            try:
                first: UpstreamChunk | None = await anext(stream)
            except StopAsyncIteration:
                first = None
            except Exception as exc:  # noqa: BLE001 - 上游失败需回退
                await self._safe(self.circuit_breaker.record_failure(str(key.id)))
                await self._record(key, model, self._latency(started), 502, picked.fallback_used)
                last_error = UpstreamError(f"上游调用失败: {exc}")
                continue

            yield ChatEvent(
                "meta",
                {
                    "model": model,
                    "pool": picked.pool,
                    "fallback": picked.fallback_used,
                    "key_id": str(key.id),
                    "conversation_id": str(conversation.id) if conversation else None,
                },
            )

            usage: dict | None = None
            mid_error: Exception | None = None
            parts: list[str] = []
            try:
                if first is not None:
                    usage = first.usage or usage
                    if first.text:
                        parts.append(first.text)
                        yield ChatEvent("delta", {"text": first.text})
                async for chunk in stream:
                    usage = chunk.usage or usage
                    if chunk.text:
                        parts.append(chunk.text)
                        yield ChatEvent("delta", {"text": chunk.text})
            except Exception as exc:  # noqa: BLE001 - 流中断无法回退
                mid_error = exc

            latency = self._latency(started)
            tokens_in = int((usage or {}).get("prompt_tokens", 0))
            tokens_out = int((usage or {}).get("completion_tokens", 0))
            total = tokens_in + tokens_out

            if mid_error is not None:
                await self._safe(self.circuit_breaker.record_failure(str(key.id)))
                await self._record(key, model, latency, 502, picked.fallback_used)
                yield ChatEvent("error", {"code": 502, "message": f"上游流中断: {mid_error}"})
                return

            await self._safe(self.rate_limiter.settle_key_tokens(key.id, spec, total))
            await self._safe(self.rate_limiter.add_user_usage(str(self.user.id), total))
            if self.user.group_id is not None:
                await self._safe(self.rate_limiter.add_group_usage(str(self.user.group_id), total))
            await self._safe(self.circuit_breaker.record_success(str(key.id)))
            await self._record(
                key, model, latency, 200, picked.fallback_used, tokens_in, tokens_out
            )

            reply = "".join(parts)
            if reply and conversation is not None and self.conversations is not None:
                await self.conversations.append_message(
                    self.user,
                    conversation,
                    "assistant",
                    reply,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                )

            if usage:
                yield ChatEvent("usage", {"tokens_in": tokens_in, "tokens_out": tokens_out})
            yield ChatEvent("done", {"finish_reason": "stop"})
            return

        if last_error is not None:
            raise last_error
        raise KeyPoolExhausted("密钥池耗尽")

    @staticmethod
    def _payload(model: str, messages: list[ChatMessage]) -> dict:
        return {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
        }

    @staticmethod
    def _latency(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)

    async def _record(
        self,
        key: ApiKey,
        model: str,
        latency_ms: int,
        status: int,
        fallback_used: bool,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> None:
        await self.audit.add(
            AuditLog(
                user_id=self.user.id,
                key_id=key.id,
                key_type="public" if key.is_public else "private",
                model=model,
                base_url_host=urlsplit(key.base_url).hostname,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency_ms,
                status=status,
                fallback_to_public=fallback_used,
            )
        )
        await self.session.commit()
