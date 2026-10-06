"""密钥调度测试：领域规则 + 服务决策。"""

from __future__ import annotations

import uuid

import pytest
from fakeredis.aioredis import FakeRedis

from app.domain.ratelimit import RateLimitSpec
from app.domain.scheduler import (
    Candidate,
    Scheduler,
    SmoothWeightedRoundRobin,
    effective_weight,
    model_matches,
    remaining_ratio,
)
from app.infra.redis_store import RedisStore
from app.models.api_key import ApiKey
from app.services.ratelimit import CircuitBreaker, RateLimiter
from app.services.scheduler import SchedulerService

BASE = 1_700_000_000.0


@pytest.fixture
async def store():
    client = FakeRedis(decode_responses=True)
    redis_store = RedisStore("redis://fake", client=client)
    yield redis_store
    await client.aclose()


def make_key(
    *,
    pool: str = "private",
    weight: int = 1,
    models: tuple[str, ...] = ("gpt-4o",),
    limits: dict | None = None,
    status: str = "active",
) -> ApiKey:
    return ApiKey(
        id=uuid.uuid4(),
        user_id=uuid.uuid4() if pool == "private" else None,
        provider_name="p",
        base_url="https://api.openai.com/v1",
        models_json=list(models),
        encrypted_key=b"",
        key_fingerprint="sk-...abcd",
        rate_limits_json=limits or {},
        weight=weight,
        status=status,
        priority_pool=pool,
    )


# --- 纯领域 ---
def test_model_matches_wildcard() -> None:
    assert model_matches(["gpt-4o", "claude-*"], "gpt-4o")
    assert model_matches(["claude-*"], "claude-sonnet-4")
    assert not model_matches(["gpt-*"], "claude-3")
    assert model_matches([], "anything")
    assert model_matches(["gpt-4o"], None)


def test_remaining_ratio_takes_min() -> None:
    spec = RateLimitSpec(rpm=100, rpd=1000)
    assert remaining_ratio(spec, {"rpm": 30, "rpd": 0}) == pytest.approx(0.7)
    assert remaining_ratio(spec, {"rpm": 0, "rpd": 900}) == pytest.approx(0.1)
    assert remaining_ratio(RateLimitSpec(), {}) == 1.0


def test_effective_weight_zero_when_unavailable() -> None:
    spec = RateLimitSpec(rpm=10)
    base = dict(key_id="k1", pool="private", spec=spec)
    assert effective_weight(Candidate(weight=2, used={"rpm": 5}, **base)) == pytest.approx(1.0)
    assert effective_weight(Candidate(weight=2, used={"rpm": 5}, circuit_open=True, **base)) == 0.0
    assert (
        effective_weight(Candidate(weight=2, used={"rpm": 5}, status_active=False, **base)) == 0.0
    )
    assert effective_weight(Candidate(weight=2, used={"rpm": 10}, **base)) == 0.0


def test_swrr_equal_weights_alternates() -> None:
    swrr = SmoothWeightedRoundRobin()
    a = Candidate("a", "private", 1, RateLimitSpec())
    b = Candidate("b", "private", 1, RateLimitSpec())
    picks = [swrr.select([a, b]).key_id for _ in range(4)]
    assert picks == ["a", "b", "a", "b"]


def test_swrr_weighted_distribution() -> None:
    swrr = SmoothWeightedRoundRobin()
    heavy = Candidate("heavy", "private", 3, RateLimitSpec())
    light = Candidate("light", "private", 1, RateLimitSpec())
    picks = [swrr.select([heavy, light]).key_id for _ in range(8)]
    assert picks.count("heavy") == 6
    assert picks.count("light") == 2


def test_scheduler_private_then_fallback() -> None:
    scheduler = Scheduler()
    private_ok = Candidate("p1", "private", 1, RateLimitSpec())
    public_ok = Candidate("pub1", "public", 1, RateLimitSpec())

    sel = scheduler.choose([private_ok], [public_ok], fallback=True)
    assert sel.key_id == "p1" and sel.fallback_used is False

    private_dead = Candidate("p2", "private", 1, RateLimitSpec(rpm=10), used={"rpm": 10})
    sel = scheduler.choose([private_dead], [public_ok], fallback=True)
    assert sel.key_id == "pub1" and sel.fallback_used is True

    sel = scheduler.choose([private_dead], [public_ok], fallback=False)
    assert sel.key_id is None and sel.reason == "no_capacity"


# --- 服务决策 ---
async def test_pick_prefers_private(store: RedisStore) -> None:
    limiter = RateLimiter(store)
    service = SchedulerService(limiter, CircuitBreaker(store))
    private = make_key(pool="private", limits={"rpm": 10})
    public = make_key(pool="public", limits={"rpm": 10})

    picked = await service.pick([private], [public], model="gpt-4o", fallback=True, now=BASE)
    assert picked is not None
    assert picked.key.id == private.id
    assert picked.fallback_used is False


async def test_pick_falls_back_when_private_exhausted(store: RedisStore) -> None:
    limiter = RateLimiter(store)
    service = SchedulerService(limiter, CircuitBreaker(store))
    private = make_key(pool="private", limits={"rpm": 1})
    public = make_key(pool="public", limits={"rpm": 10})

    # 私有 Key 用满窗口配额
    await limiter.consume_key_request(private.id, RateLimitSpec(rpm=1), now=BASE)

    picked = await service.pick([private], [public], model="gpt-4o", fallback=True, now=BASE)
    assert picked is not None
    assert picked.key.id == public.id
    assert picked.fallback_used is True


async def test_pick_no_capacity_without_fallback(store: RedisStore) -> None:
    limiter = RateLimiter(store)
    service = SchedulerService(limiter, CircuitBreaker(store))
    private = make_key(pool="private", limits={"rpm": 1})
    public = make_key(pool="public", limits={"rpm": 10})
    await limiter.consume_key_request(private.id, RateLimitSpec(rpm=1), now=BASE)

    picked = await service.pick([private], [public], model="gpt-4o", fallback=False, now=BASE)
    assert picked is None


async def test_pick_skips_open_circuit(store: RedisStore) -> None:
    limiter = RateLimiter(store)
    breaker = CircuitBreaker(store, threshold=2, cooldown=60)
    service = SchedulerService(limiter, breaker)
    key = make_key(pool="private", limits={"rpm": 10})

    await breaker.record_failure(str(key.id), now=BASE)
    await breaker.record_failure(str(key.id), now=BASE)

    assert await breaker.is_blocked(str(key.id), now=BASE) is True
    assert await service.pick([key], [], now=BASE) is None

    # 冷却结束后可再次被调度
    picked = await service.pick([key], [], now=BASE + 61)
    assert picked is not None and picked.key.id == key.id


async def test_pick_filters_by_model(store: RedisStore) -> None:
    limiter = RateLimiter(store)
    service = SchedulerService(limiter, CircuitBreaker(store))
    key = make_key(models=("gpt-4o",))

    assert await service.pick([key], [], model="claude-3", now=BASE) is None
    assert await service.pick([key], [], model="gpt-4o", now=BASE) is not None


async def test_pick_skips_disabled_key(store: RedisStore) -> None:
    limiter = RateLimiter(store)
    service = SchedulerService(limiter, CircuitBreaker(store))
    key = make_key(status="disabled")
    assert await service.pick([key], [], now=BASE) is None
