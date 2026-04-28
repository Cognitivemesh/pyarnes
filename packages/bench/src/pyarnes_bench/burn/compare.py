"""Side-by-side model comparison.

Takes two sets of :class:`SessionKpis` (one per model) and produces a
:class:`ModelComparison` record carrying the diffs that matter when a
team is choosing between models.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pyarnes_bench.burn.kpis import SessionKpis

__all__ = [
    "ModelComparison",
    "ModelStats",
    "compare_models",
]


@dataclass(frozen=True, slots=True)
class ModelStats:
    """Aggregated KPI averages for one model across many sessions."""

    model: str
    sessions: int
    avg_one_shot_rate: float
    total_retry_loops: int
    avg_cache_hit_rate: float
    cost_total: Decimal
    cost_per_call: Decimal
    total_calls: int

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict."""
        return {
            "model": self.model,
            "sessions": self.sessions,
            "avg_one_shot_rate": self.avg_one_shot_rate,
            "total_retry_loops": self.total_retry_loops,
            "avg_cache_hit_rate": self.avg_cache_hit_rate,
            "cost_total": str(self.cost_total),
            "cost_per_call": str(self.cost_per_call),
            "total_calls": self.total_calls,
        }


@dataclass(frozen=True, slots=True)
class ModelComparison:
    """Two :class:`ModelStats` placed side-by-side."""

    a: ModelStats
    b: ModelStats

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict."""
        return {"a": self.a.as_dict(), "b": self.b.as_dict()}


def compare_models(
    a: str,
    b: str,
    sessions_by_model: Mapping[str, Sequence[SessionKpis]],
) -> ModelComparison:
    """Return a :class:`ModelComparison` for *a* vs *b*.

    Args:
        a: First model identifier.
        b: Second model identifier.
        sessions_by_model: Map from model id to that model's sessions.
            Missing keys produce zero-valued stats.
    """
    return ModelComparison(
        a=_stats(a, sessions_by_model.get(a, [])),
        b=_stats(b, sessions_by_model.get(b, [])),
    )


def _stats(model: str, sessions: Sequence[SessionKpis]) -> ModelStats:
    if not sessions:
        return ModelStats(
            model=model,
            sessions=0,
            avg_one_shot_rate=0.0,
            total_retry_loops=0,
            avg_cache_hit_rate=0.0,
            cost_total=Decimal(0),
            cost_per_call=Decimal(0),
            total_calls=0,
        )
    n = len(sessions)
    total_calls = sum(s.total_calls for s in sessions)
    cost_total = sum((s.cost_total for s in sessions), Decimal(0))
    cost_per_call = cost_total / Decimal(total_calls) if total_calls else Decimal(0)
    return ModelStats(
        model=model,
        sessions=n,
        avg_one_shot_rate=sum(s.one_shot_rate for s in sessions) / n,
        total_retry_loops=sum(s.retry_loops for s in sessions),
        avg_cache_hit_rate=sum(s.cache_hit_rate for s in sessions) / n,
        cost_total=cost_total,
        cost_per_call=cost_per_call,
        total_calls=total_calls,
    )
