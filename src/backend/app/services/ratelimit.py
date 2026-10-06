"""限流与熔断服务：组合领域规则与 Redis 存储。

三层兜底（Key → 用户 → IP）与日配额由调用方编排；本模块提供原子原语。
"""

from __future__ import annotations

import time

from app.domain.ratelimit import (
    REQUEST_DIMENSIONS,
    TOKEN_DIMENSIONS,
    CircuitState,
    Dimension,
    LimitDecision,
    QuotaDecision,
    RateLimitSpec,
    build_counters,
)
from app.infra.redis_store import RedisStore


class RateLimiter:
    def __init__(self, store: RedisStore, *, prefix: str = "rl") -> None:
        self.store = store
        self.prefix = prefix

    # --- 请求维度（RPM/RPH/RPD）：检查并占用 ---
    async def consume_request(
        self, *, scope: str, identifier: str, spec: RateLimitSpec, now: float | None = None
    ) -> LimitDecision:
        moment = time.time() if now is None else now
        counters = build_counters(
            scope=scope,
            identifier=identifier,
            spec=spec,
            dimensions=REQUEST_DIMENSIONS,
            delta=1,
            now=moment,
            prefix=self.prefix,
        )
        return await self.store.check_and_consume(counters)

    async def consume_key_request(
        self, key_id: str, spec: RateLimitSpec, *, now: float | None = None
    ) -> LimitDecision:
        return await self.consume_request(scope="key", identifier=str(key_id), spec=spec, now=now)

    async def consume_user_request(
        self, user_id: str, spec: RateLimitSpec, *, now: float | None = None
    ) -> LimitDecision:
        return await self.consume_request(scope="user", identifier=str(user_id), spec=spec, now=now)

    async def consume_ip_request(
        self, ip: str, spec: RateLimitSpec, *, now: float | None = None
    ) -> LimitDecision:
        return await self.consume_request(scope="ip", identifier=ip, spec=spec, now=now)

    # --- Token 维度（TPM/TPH/TPD）：请求前预检、响应后结算 ---
    async def precheck_tokens(
        self,
        *,
        scope: str,
        identifier: str,
        spec: RateLimitSpec,
        now: float | None = None,
    ) -> LimitDecision:
        moment = time.time() if now is None else now
        counters = build_counters(
            scope=scope,
            identifier=identifier,
            spec=spec,
            dimensions=TOKEN_DIMENSIONS,
            delta=0,
            now=moment,
            prefix=self.prefix,
        )
        return await self.store.check_and_consume(counters)

    async def settle_tokens(
        self,
        *,
        scope: str,
        identifier: str,
        spec: RateLimitSpec,
        tokens: int,
        now: float | None = None,
    ) -> None:
        moment = time.time() if now is None else now
        counters = build_counters(
            scope=scope,
            identifier=identifier,
            spec=spec,
            dimensions=TOKEN_DIMENSIONS,
            delta=max(0, tokens),
            now=moment,
            prefix=self.prefix,
        )
        await self.store.consume(counters)

    async def precheck_key_tokens(
        self, key_id: str, spec: RateLimitSpec, *, now: float | None = None
    ) -> LimitDecision:
        return await self.precheck_tokens(scope="key", identifier=str(key_id), spec=spec, now=now)

    async def settle_key_tokens(
        self,
        key_id: str,
        spec: RateLimitSpec,
        tokens: int,
        *,
        now: float | None = None,
    ) -> None:
        await self.settle_tokens(
            scope="key", identifier=str(key_id), spec=spec, tokens=tokens, now=now
        )

    # --- 当前窗口用量（供调度器计算剩余配额比例）---
    async def current_usage(
        self,
        *,
        scope: str,
        identifier: str,
        spec: RateLimitSpec,
        now: float | None = None,
    ) -> dict[str, int]:
        moment = time.time() if now is None else now
        counters = build_counters(
            scope=scope,
            identifier=identifier,
            spec=spec,
            dimensions=tuple(Dimension),
            delta=0,
            now=moment,
            prefix=self.prefix,
        )
        values = await self.store.get_many_int([c.key for c in counters])
        return {c.dimension.value: v for c, v in zip(counters, values, strict=True)}

    async def current_key_usage(
        self, key_id: str, spec: RateLimitSpec, *, now: float | None = None
    ) -> dict[str, int]:
        return await self.current_usage(scope="key", identifier=str(key_id), spec=spec, now=now)

    # --- 日配额 ---
    async def check_user_quota(
        self,
        user_id: str,
        limit: int,
        *,
        now: float | None = None,
        estimated_tokens: int = 0,
    ) -> QuotaDecision:
        moment = time.time() if now is None else now
        return await self.store.check_quota(
            "user", str(user_id), limit, now=moment, estimated_tokens=estimated_tokens
        )

    async def add_user_usage(self, user_id: str, tokens: int, *, now: float | None = None) -> int:
        moment = time.time() if now is None else now
        return await self.store.add_quota("user", str(user_id), tokens, now=moment)

    async def check_group_quota(
        self,
        group_id: str,
        limit: int,
        *,
        now: float | None = None,
        estimated_tokens: int = 0,
    ) -> QuotaDecision:
        moment = time.time() if now is None else now
        return await self.store.check_quota(
            "group", str(group_id), limit, now=moment, estimated_tokens=estimated_tokens
        )

    async def add_group_usage(self, group_id: str, tokens: int, *, now: float | None = None) -> int:
        moment = time.time() if now is None else now
        return await self.store.add_quota("group", str(group_id), tokens, now=moment)


class CircuitBreaker:
    """上游 Key 熔断：连续失败达阈值后隔离，冷却后半开探测恢复（见 §4.5）。"""

    def __init__(self, store: RedisStore, *, threshold: int = 5, cooldown: int = 60) -> None:
        self.store = store
        self.threshold = threshold
        self.cooldown = cooldown

    async def allow(self, key_id: str, *, now: float | None = None) -> bool:
        moment = time.time() if now is None else now
        return await self.store.circuit_allow(key_id, cooldown=self.cooldown, now=moment)

    async def record_failure(self, key_id: str, *, now: float | None = None) -> CircuitState:
        moment = time.time() if now is None else now
        return await self.store.circuit_record_failure(
            key_id, threshold=self.threshold, cooldown=self.cooldown, now=moment
        )

    async def record_success(self, key_id: str) -> None:
        await self.store.circuit_record_success(key_id)

    async def state(self, key_id: str) -> CircuitState:
        return await self.store.circuit_state(key_id)

    async def is_blocked(self, key_id: str, *, now: float | None = None) -> bool:
        moment = time.time() if now is None else now
        return await self.store.circuit_is_blocked(key_id, cooldown=self.cooldown, now=moment)

    async def reset(self, key_id: str) -> None:
        await self.store.reset_circuit(key_id)
