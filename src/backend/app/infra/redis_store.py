"""Redis 访问层：原子限流计数、日配额、熔断状态（见设计说明书 §5）。

- 限流采用固定窗口 + 键内含窗口起点，天然过期；
- 检查与自增在单条 Lua 脚本内完成（全有或全无），避免并发下超限；
- 客户端惰性创建，Redis 不可用时通过异常冒泡，由上层决定降级策略。
"""

from __future__ import annotations

from typing import Any

from redis.asyncio import Redis

from app.domain.ratelimit import (
    CircuitState,
    Counter,
    Dimension,
    LimitDecision,
    QuotaDecision,
    circuit_keys,
    quota_key,
    seconds_until_utc_midnight,
    utc_date,
)

# KEYS = 计数器键；ARGV = (limit, delta, ttl) 三元组
# 返回 {命中下标, 当前值, 上限}；下标 0 表示全部通过并已完成自增
_CHECK_AND_CONSUME = """
local n = #KEYS
for i=1,n do
  local limit = tonumber(ARGV[(i-1)*3+1])
  local delta = tonumber(ARGV[(i-1)*3+2])
  local current = tonumber(redis.call('GET', KEYS[i]) or '0')
  if limit > 0 and current + delta > limit then
    return {i, current, limit}
  end
end
for i=1,n do
  local delta = tonumber(ARGV[(i-1)*3+2])
  local ttl = tonumber(ARGV[(i-1)*3+3])
  if delta > 0 then
    redis.call('INCRBY', KEYS[i], delta)
    redis.call('EXPIRE', KEYS[i], ttl)
  end
end
return {0, 0, 0}
"""

# 仅自增（用于响应后精确记账）
_CONSUME = """
local n = #KEYS
for i=1,n do
  local delta = tonumber(ARGV[(i-1)*2+1])
  local ttl = tonumber(ARGV[(i-1)*2+2])
  if delta > 0 then
    redis.call('INCRBY', KEYS[i], delta)
    redis.call('EXPIRE', KEYS[i], ttl)
  end
end
return 1
"""


class RedisStore:
    def __init__(self, url: str, *, client: Redis | None = None) -> None:
        self.url = url
        self._client = client

    @property
    def client(self) -> Redis:
        if self._client is None:
            self._client = Redis.from_url(self.url, decode_responses=True)
        return self._client

    async def ping(self) -> bool:
        try:
            return bool(await self.client.ping())
        except Exception:  # noqa: BLE001 - 健康检查不应抛出
            return False

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # --- 通用 ---
    async def get_int(self, key: str) -> int:
        value = await self.client.get(key)
        return int(value) if value is not None else 0

    async def incr(self, key: str, *, ttl: int | None = None, amount: int = 1) -> int:
        value = await self.client.incrby(key, amount)
        if ttl is not None and value == amount:
            await self.client.expire(key, ttl)
        return int(value)

    async def delete(self, *keys: str) -> None:
        if keys:
            await self.client.delete(*keys)

    # --- 限流 ---
    async def check_and_consume(self, counters: list[Counter]) -> LimitDecision:
        if not counters:
            return LimitDecision.ok()
        keys = [c.key for c in counters]
        args: list[Any] = []
        for counter in counters:
            args.extend(counter.to_redis_args())

        result = await self.client.eval(_CHECK_AND_CONSUME, len(keys), *keys, *args)
        index, current, limit = (int(result[0]), int(result[1]), int(result[2]))
        if index == 0:
            return LimitDecision.ok()
        return LimitDecision.blocked(counters[index - 1].dimension, limit, current)

    async def consume(self, counters: list[Counter]) -> None:
        """不检查、仅自增（响应后结算）。"""
        if not counters:
            return
        keys = [c.key for c in counters]
        args: list[Any] = []
        for counter in counters:
            args.extend((str(counter.delta), str(counter.ttl)))
        await self.client.eval(_CONSUME, len(keys), *keys, *args)

    # --- 日配额 ---
    async def get_quota(self, scope: str, identifier: str, *, now: float) -> int:
        return await self.get_int(quota_key(scope, identifier, utc_date(now)))

    async def check_quota(
        self,
        scope: str,
        identifier: str,
        limit: int,
        *,
        now: float,
        estimated_tokens: int = 0,
    ) -> QuotaDecision:
        if limit <= 0:
            return QuotaDecision.ok()
        used = await self.get_quota(scope, identifier, now=now)
        if used + estimated_tokens > limit:
            return QuotaDecision.blocked(used, limit)
        return QuotaDecision.ok(used=used, limit=limit)

    async def add_quota(self, scope: str, identifier: str, tokens: int, *, now: float) -> int:
        if tokens <= 0:
            return await self.get_quota(scope, identifier, now=now)
        key = quota_key(scope, identifier, utc_date(now))
        value = await self.client.incrby(key, tokens)
        await self.client.expire(key, seconds_until_utc_midnight(now))
        return int(value)

    # --- 熔断 ---
    async def circuit_state(self, key_id: str) -> CircuitState:
        value = await self.client.get(circuit_keys(key_id)["state"])
        return CircuitState(value) if value else CircuitState.CLOSED

    async def circuit_allow(self, key_id: str, *, cooldown: int, now: float) -> bool:
        """closed 放行；open 冷却结束后进入 half_open 并只放行一个探测请求。"""
        keys = circuit_keys(key_id)
        state = await self.circuit_state(key_id)
        if state is CircuitState.CLOSED:
            return True
        if state is CircuitState.OPEN:
            opened_at = await self.get_int(keys["opened_at"])
            if now - opened_at < cooldown:
                return False
            await self.client.set(keys["state"], CircuitState.HALF_OPEN.value)
            await self.client.delete(keys["probe"])
        granted = await self.client.set(keys["probe"], "1", nx=True, ex=cooldown)
        return bool(granted)

    async def circuit_record_failure(
        self, key_id: str, *, threshold: int, cooldown: int, now: float
    ) -> CircuitState:
        keys = circuit_keys(key_id)
        failures = await self.incr(keys["failures"], ttl=cooldown * 2, amount=1)
        if failures >= threshold:
            await self.client.set(keys["state"], CircuitState.OPEN.value)
            await self.client.set(keys["opened_at"], int(now))
            await self.client.expire(keys["opened_at"], cooldown * 2)
            return CircuitState.OPEN
        return await self.circuit_state(key_id)

    async def circuit_record_success(self, key_id: str) -> None:
        await self.delete(*circuit_keys(key_id).values())

    async def reset_circuit(self, key_id: str) -> None:
        await self.delete(*circuit_keys(key_id).values())


__all__ = ["Dimension", "RedisStore"]
