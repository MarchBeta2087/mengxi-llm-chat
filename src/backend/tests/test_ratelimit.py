"""限流 / 配额 / 熔断测试（fakeredis 作为 Redis 替身）。"""

from __future__ import annotations

import asyncio
import datetime as dt

import pytest
from fakeredis.aioredis import FakeRedis

from app.domain.ratelimit import (
    Dimension,
    RateLimitSpec,
    build_counters,
    seconds_until_utc_midnight,
    window_start,
)
from app.infra.redis_store import RedisStore
from app.services.ratelimit import CircuitBreaker, RateLimiter

BASE = 1_700_000_000.0  # 固定时间戳，保证窗口确定性


@pytest.fixture
async def store():
    client = FakeRedis(decode_responses=True)
    redis_store = RedisStore("redis://fake", client=client)
    yield redis_store
    await client.aclose()


# --- 纯领域规则 ---
def test_window_start_aligns() -> None:
    assert window_start(125.9, 60) == 120
    assert window_start(0, 3600) == 0


def test_build_counters_skips_unlimited() -> None:
    spec = RateLimitSpec(rpm=10, rpd=100)
    counters = build_counters(
        scope="key",
        identifier="k1",
        spec=spec,
        dimensions=(Dimension.RPM, Dimension.RPH, Dimension.RPD),
        delta=1,
        now=BASE,
    )
    assert {c.dimension for c in counters} == {Dimension.RPM, Dimension.RPD}


def test_seconds_until_utc_midnight() -> None:
    now = dt.datetime(2026, 10, 6, 23, 59, 0, tzinfo=dt.UTC).timestamp()
    assert seconds_until_utc_midnight(now) == 60


# --- 请求维度 ---
async def test_rpm_enforced(store: RedisStore) -> None:
    limiter = RateLimiter(store)
    spec = RateLimitSpec(rpm=2)
    assert (await limiter.consume_key_request("k1", spec, now=BASE)).allowed
    assert (await limiter.consume_key_request("k1", spec, now=BASE)).allowed

    decision = await limiter.consume_key_request("k1", spec, now=BASE)
    assert not decision.allowed
    assert decision.dimension is Dimension.RPM
    assert decision.limit == 2


async def test_window_rolls_over(store: RedisStore) -> None:
    limiter = RateLimiter(store)
    spec = RateLimitSpec(rpm=1)
    assert (await limiter.consume_key_request("k1", spec, now=BASE)).allowed
    assert not (await limiter.consume_key_request("k1", spec, now=BASE)).allowed
    assert (await limiter.consume_key_request("k1", spec, now=BASE + 60)).allowed


async def test_unlimited_never_blocks_and_writes_no_keys(store: RedisStore) -> None:
    limiter = RateLimiter(store)
    spec = RateLimitSpec()
    for _ in range(50):
        assert (await limiter.consume_key_request("k1", spec, now=BASE)).allowed
    assert await store.client.keys("rl:*") == []


async def test_keys_are_isolated(store: RedisStore) -> None:
    limiter = RateLimiter(store)
    spec = RateLimitSpec(rpm=1)
    assert (await limiter.consume_key_request("k1", spec, now=BASE)).allowed
    assert not (await limiter.consume_key_request("k1", spec, now=BASE)).allowed
    assert (await limiter.consume_key_request("k2", spec, now=BASE)).allowed


async def test_three_tier_scopes_isolated(store: RedisStore) -> None:
    limiter = RateLimiter(store)
    spec = RateLimitSpec(rpm=1)
    assert (await limiter.consume_key_request("k1", spec, now=BASE)).allowed
    assert (await limiter.consume_user_request("u1", spec, now=BASE)).allowed
    assert (await limiter.consume_ip_request("1.2.3.4", spec, now=BASE)).allowed
    assert not (await limiter.consume_ip_request("1.2.3.4", spec, now=BASE)).allowed


# --- Token 维度 ---
async def test_concurrent_limit_accuracy(store: RedisStore) -> None:
    """并发下原子检查应精确卡在限额（验收：误差 < 5% → 实际 0%）。"""
    limiter = RateLimiter(store)
    spec = RateLimitSpec(rpm=10)
    results = await asyncio.gather(
        *(limiter.consume_key_request("k1", spec, now=BASE) for _ in range(200))
    )
    allowed = sum(1 for r in results if r.allowed)
    assert allowed == 10


async def test_token_precheck_and_settle(store: RedisStore) -> None:
    limiter = RateLimiter(store)
    spec = RateLimitSpec(tpm=100)
    assert (await limiter.precheck_key_tokens("k1", spec, now=BASE)).allowed

    await limiter.settle_key_tokens("k1", spec, 60, now=BASE)
    assert (await limiter.precheck_key_tokens("k1", spec, now=BASE)).allowed

    await limiter.settle_key_tokens("k1", spec, 60, now=BASE)  # 累计 120 > 100
    decision = await limiter.precheck_key_tokens("k1", spec, now=BASE)
    assert not decision.allowed
    assert decision.dimension is Dimension.TPM


# --- 日配额 ---
async def test_user_quota(store: RedisStore) -> None:
    limiter = RateLimiter(store)
    now = dt.datetime(2026, 10, 6, 12, 0, tzinfo=dt.UTC).timestamp()
    assert (await limiter.check_user_quota("u1", 100, now=now, estimated_tokens=80)).allowed

    await limiter.add_user_usage("u1", 80, now=now)
    assert not (await limiter.check_user_quota("u1", 100, now=now, estimated_tokens=30)).allowed
    assert (await limiter.check_user_quota("u1", 100, now=now, estimated_tokens=10)).allowed


async def test_quota_resets_next_day(store: RedisStore) -> None:
    limiter = RateLimiter(store)
    day1 = dt.datetime(2026, 10, 6, 23, 0, tzinfo=dt.UTC).timestamp()
    day2 = dt.datetime(2026, 10, 7, 1, 0, tzinfo=dt.UTC).timestamp()
    await limiter.add_user_usage("u1", 100, now=day1)
    assert (
        await limiter.check_user_quota("u1", 100, now=day1, estimated_tokens=1)
    ).allowed is False
    assert (await limiter.check_user_quota("u1", 100, now=day2, estimated_tokens=1)).allowed is True


async def test_group_quota_separate_from_user(store: RedisStore) -> None:
    limiter = RateLimiter(store)
    now = dt.datetime(2026, 10, 6, 12, 0, tzinfo=dt.UTC).timestamp()
    await limiter.add_user_usage("u1", 50, now=now)
    await limiter.add_group_usage("g1", 90, now=now)
    assert (await limiter.check_group_quota("g1", 100, now=now)).used == 90
    assert (await limiter.check_user_quota("u1", 100, now=now)).used == 50


# --- 熔断 ---
async def test_circuit_breaker_lifecycle(store: RedisStore) -> None:
    breaker = CircuitBreaker(store, threshold=3, cooldown=60)
    assert await breaker.allow("k1", now=BASE) is True

    for _ in range(3):
        state = await breaker.record_failure("k1", now=BASE)
    assert state.value == "open"

    assert await breaker.allow("k1", now=BASE) is False
    assert await breaker.allow("k1", now=BASE + 30) is False

    # 冷却结束：转半开，放行一个探测请求
    assert await breaker.allow("k1", now=BASE + 61) is True
    assert await breaker.allow("k1", now=BASE + 61) is False

    await breaker.record_success("k1")
    assert await breaker.state("k1") == "closed"
    assert await breaker.allow("k1", now=BASE + 61) is True


async def test_circuit_failure_below_threshold_keeps_closed(store: RedisStore) -> None:
    breaker = CircuitBreaker(store, threshold=5, cooldown=60)
    await breaker.record_failure("k1", now=BASE)
    await breaker.record_failure("k1", now=BASE)
    assert await breaker.allow("k1", now=BASE) is True
    assert await breaker.state("k1") == "closed"
