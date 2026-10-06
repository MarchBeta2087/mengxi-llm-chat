"""密钥调度领域逻辑：配额感知平滑加权轮询（SWRR）+ 私有优先与回退决策。

纯逻辑，不依赖 Redis/DB，便于单测（见设计说明书 §4.5）。
"""

from __future__ import annotations

import fnmatch
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.domain.ratelimit import Dimension, RateLimitSpec


def model_matches(models: Sequence[str], model: str | None) -> bool:
    """模型匹配，支持通配（如 ``gpt-*``）。``model`` 为 None 表示不限。"""
    if model is None:
        return True
    if not models:
        return True
    return any(fnmatch.fnmatchcase(model, pattern) for pattern in models)


@dataclass(frozen=True)
class Candidate:
    """调度候选 Key。"""

    key_id: str
    pool: str
    weight: int
    spec: RateLimitSpec
    used: dict[str, int] = field(default_factory=dict)
    circuit_open: bool = False
    status_active: bool = True


def remaining_ratio(spec: RateLimitSpec, used: dict[str, int]) -> float:
    """剩余配额比例：取所有已配置维度余量的最小值，范围 [0, 1]。"""
    ratios: list[float] = []
    for dimension in Dimension:
        limit = spec.limit_for(dimension)
        if limit <= 0:
            continue
        current = used.get(dimension.value, 0)
        ratios.append(max(0.0, 1.0 - current / limit))
    return min(ratios) if ratios else 1.0


def effective_weight(candidate: Candidate) -> float:
    """有效权重 = 基准权重 × 剩余配额比例；不可用的 Key 权重为 0。"""
    if not candidate.status_active or candidate.circuit_open:
        return 0.0
    return max(0.0, float(candidate.weight)) * remaining_ratio(candidate.spec, candidate.used)


def is_eligible(candidate: Candidate) -> bool:
    return effective_weight(candidate) > 0.0


@dataclass(frozen=True)
class Selection:
    key_id: str | None
    pool: str | None
    fallback_used: bool
    reason: str  # private | fallback_public | no_capacity


class SmoothWeightedRoundRobin:
    """Nginx SWRR：按有效权重平滑选取，避免瞬时打到同一 Key。

    实例持有跨请求的 ``current_weight`` 状态（单实例内存态；多实例可迁到 Redis）。
    """

    def __init__(self) -> None:
        self._current: dict[str, float] = {}

    def select(self, candidates: Sequence[Candidate]) -> Candidate | None:
        eligible = [c for c in candidates if is_eligible(c)]
        if not eligible:
            return None

        total = 0.0
        best: Candidate | None = None
        best_weight: float | None = None
        for candidate in eligible:
            weight = effective_weight(candidate)
            current = self._current.get(candidate.key_id, 0.0) + weight
            self._current[candidate.key_id] = current
            total += weight
            if best_weight is None or current > best_weight:
                best = candidate
                best_weight = current

        assert best is not None
        self._current[best.key_id] -= total
        return best

    def forget(self, key_id: str) -> None:
        self._current.pop(key_id, None)


class Scheduler:
    """私有优先 → （可选）回退公有 → 无容量。"""

    def __init__(self, swrr: SmoothWeightedRoundRobin | None = None) -> None:
        self.swrr = swrr or SmoothWeightedRoundRobin()

    def choose(
        self,
        private: Sequence[Candidate],
        public: Sequence[Candidate],
        *,
        fallback: bool,
    ) -> Selection:
        picked = self.swrr.select(private)
        if picked is not None:
            return Selection(picked.key_id, picked.pool, False, "private")

        if fallback:
            picked = self.swrr.select(public)
            if picked is not None:
                return Selection(picked.key_id, picked.pool, True, "fallback_public")

        return Selection(None, None, False, "no_capacity")
