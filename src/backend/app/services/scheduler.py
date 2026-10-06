"""调度服务：从数据库候选集 + Redis 用量构造调度决策（见设计说明书 §4.5）。"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass

from redis.exceptions import RedisError

from app.domain.ratelimit import RateLimitSpec
from app.domain.scheduler import Candidate, Scheduler, Selection, model_matches
from app.models.api_key import ApiKey
from app.services.ratelimit import CircuitBreaker, RateLimiter


@dataclass
class ScheduledKey:
    key: ApiKey
    pool: str
    fallback_used: bool


class SchedulerService:
    def __init__(
        self,
        rate_limiter: RateLimiter,
        circuit_breaker: CircuitBreaker,
        *,
        scheduler: Scheduler | None = None,
    ) -> None:
        self.rate_limiter = rate_limiter
        self.circuit_breaker = circuit_breaker
        self.scheduler = scheduler or Scheduler()

    async def _build_candidates(
        self, keys: Sequence[ApiKey], *, model: str | None, now: float
    ) -> list[Candidate]:
        candidates: list[Candidate] = []
        for key in keys:
            if not key.is_active:
                continue
            if not model_matches(list(key.models_json or []), model):
                continue

            spec = RateLimitSpec.from_mapping(key.rate_limits_json)
            # Redis 不可用时降级：视为无用量/未熔断，按权重调度（风险 R4）
            try:
                used = await self.rate_limiter.current_key_usage(key.id, spec, now=now)
            except RedisError:
                used = {}
            try:
                blocked = await self.circuit_breaker.is_blocked(str(key.id), now=now)
            except RedisError:
                blocked = False
            candidates.append(
                Candidate(
                    key_id=str(key.id),
                    pool=key.priority_pool,
                    weight=key.weight,
                    spec=spec,
                    used=used,
                    circuit_open=blocked,
                    status_active=key.is_active,
                )
            )
        return candidates

    async def pick(
        self,
        private_keys: Sequence[ApiKey],
        public_keys: Sequence[ApiKey],
        *,
        model: str | None = None,
        fallback: bool = True,
        now: float | None = None,
    ) -> ScheduledKey | None:
        moment = time.time() if now is None else now
        private_candidates = await self._build_candidates(private_keys, model=model, now=moment)
        public_candidates = await self._build_candidates(public_keys, model=model, now=moment)

        selection: Selection = self.scheduler.choose(
            private_candidates, public_candidates, fallback=fallback
        )
        if selection.key_id is None:
            return None

        catalog = {str(k.id): k for k in (*private_keys, *public_keys)}
        key = catalog.get(selection.key_id)
        if key is None:  # pragma: no cover - 理论不可达
            return None
        return ScheduledKey(
            key=key, pool=selection.pool or key.priority_pool, fallback_used=selection.fallback_used
        )
