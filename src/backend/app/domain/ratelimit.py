"""限流 / 配额 / 熔断的纯领域规则（不依赖 Redis，便于单测）。

- 六维：RPM/RPH/RPD（请求）与 TPM/TPH/TPD（Token）
- 固定窗口对齐到纪元时间片，键包含窗口起点，天然过期
- 配额按 UTC 自然日
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum


class Dimension(StrEnum):
    RPM = "rpm"
    RPH = "rph"
    RPD = "rpd"
    TPM = "tpm"
    TPH = "tph"
    TPD = "tpd"


REQUEST_DIMENSIONS: tuple[Dimension, ...] = (
    Dimension.RPM,
    Dimension.RPH,
    Dimension.RPD,
)
TOKEN_DIMENSIONS: tuple[Dimension, ...] = (
    Dimension.TPM,
    Dimension.TPH,
    Dimension.TPD,
)

WINDOW_SECONDS: dict[Dimension, int] = {
    Dimension.RPM: 60,
    Dimension.RPH: 3600,
    Dimension.RPD: 86400,
    Dimension.TPM: 60,
    Dimension.TPH: 3600,
    Dimension.TPD: 86400,
}


@dataclass(frozen=True)
class RateLimitSpec:
    """六维限流配置，0 表示不限。"""

    rpm: int = 0
    rph: int = 0
    rpd: int = 0
    tpm: int = 0
    tph: int = 0
    tpd: int = 0

    @classmethod
    def from_mapping(cls, data: dict | None) -> RateLimitSpec:
        data = data or {}
        return cls(
            rpm=int(data.get("rpm", 0) or 0),
            rph=int(data.get("rph", 0) or 0),
            rpd=int(data.get("rpd", 0) or 0),
            tpm=int(data.get("tpm", 0) or 0),
            tph=int(data.get("tph", 0) or 0),
            tpd=int(data.get("tpd", 0) or 0),
        )

    def limit_for(self, dimension: Dimension) -> int:
        return int(getattr(self, dimension.value))

    @property
    def is_unlimited(self) -> bool:
        return all(self.limit_for(d) <= 0 for d in Dimension)


@dataclass(frozen=True)
class LimitDecision:
    allowed: bool
    dimension: Dimension | None = None
    limit: int = 0
    current: int = 0

    @classmethod
    def ok(cls) -> LimitDecision:
        return cls(allowed=True)

    @classmethod
    def blocked(cls, dimension: Dimension, limit: int, current: int) -> LimitDecision:
        return cls(allowed=False, dimension=dimension, limit=limit, current=current)


@dataclass(frozen=True)
class Counter:
    """一次原子计数操作的描述。"""

    dimension: Dimension
    key: str
    limit: int
    delta: int
    ttl: int

    def to_redis_args(self) -> tuple[str, str, str]:
        return (str(self.limit), str(self.delta), str(self.ttl))


def window_start(now: float, seconds: int) -> int:
    return int(now // seconds) * seconds


def build_counters(
    *,
    scope: str,
    identifier: str,
    spec: RateLimitSpec,
    dimensions: tuple[Dimension, ...],
    delta: int,
    now: float,
    prefix: str = "rl",
) -> list[Counter]:
    """构造计数操作列表；limit=0 且 delta=0 的维度直接跳过。"""
    counters: list[Counter] = []
    for dimension in dimensions:
        limit = spec.limit_for(dimension)
        if limit <= 0:
            continue  # 不限的维度无需计数
        ttl = WINDOW_SECONDS[dimension]
        start = window_start(now, ttl)
        key = f"{prefix}:{scope}:{identifier}:{dimension.value}:{start}"
        counters.append(Counter(dimension, key, limit, delta, ttl))
    return counters


# --- 日配额 ---


@dataclass(frozen=True)
class QuotaDecision:
    allowed: bool
    used: int = 0
    limit: int = 0

    @classmethod
    def ok(cls, *, used: int = 0, limit: int = 0) -> QuotaDecision:
        return cls(allowed=True, used=used, limit=limit)

    @classmethod
    def blocked(cls, used: int, limit: int) -> QuotaDecision:
        return cls(allowed=False, used=used, limit=limit)


def utc_date(now: float) -> str:
    return dt.datetime.fromtimestamp(now, tz=dt.UTC).strftime("%Y-%m-%d")


def quota_key(scope: str, identifier: str, date: str, *, prefix: str = "quota") -> str:
    return f"{prefix}:{scope}:{identifier}:{date}"


def seconds_until_utc_midnight(now: float) -> int:
    moment = dt.datetime.fromtimestamp(now, tz=dt.UTC)
    tomorrow = (moment + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((tomorrow - moment).total_seconds()))


# --- 熔断 ---


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


def circuit_keys(key_id: str, *, prefix: str = "cb") -> dict[str, str]:
    base = f"{prefix}:{key_id}"
    return {
        "state": f"{base}:state",
        "failures": f"{base}:failures",
        "opened_at": f"{base}:opened_at",
        "probe": f"{base}:probe",
    }
