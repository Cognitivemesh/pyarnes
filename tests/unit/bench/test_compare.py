"""Tests for ``compare_models`` — A/B model comparison."""

from __future__ import annotations

from decimal import Decimal

from pyarnes_bench.burn.compare import compare_models
from pyarnes_bench.burn.kpis import SessionKpis


def _kpis(model_id: str, calls: int = 10, cost: str = "0.05") -> SessionKpis:
    return SessionKpis(
        session_id=f"sess-{model_id}",
        project="proj",
        total_calls=calls,
        unique_tools=3,
        one_shot_rate=0.8,
        retry_loops=1,
        cache_hit_rate=0.5,
        read_edit_ratio=2.0,
        cost_total=Decimal(cost),
        currency="USD",
        cost_by_bucket={},
        cost_by_tool={},
    )


class TestCompareModels:
    def test_two_model_summary(self) -> None:
        sessions = {
            "model-a": [_kpis("a", calls=10, cost="0.10"), _kpis("a", calls=20, cost="0.20")],
            "model-b": [_kpis("b", calls=15, cost="0.30")],
        }
        comp = compare_models("model-a", "model-b", sessions)
        assert comp.a.model == "model-a"
        assert comp.a.sessions == 2
        assert comp.a.total_calls == 30
        assert comp.a.cost_total == Decimal("0.30")
        # cost_per_call = 0.30 / 30 = 0.01
        assert comp.a.cost_per_call == Decimal("0.30") / Decimal(30)
        assert comp.b.model == "model-b"
        assert comp.b.sessions == 1
        assert comp.b.total_calls == 15

    def test_missing_model_yields_zero_stats(self) -> None:
        comp = compare_models("missing-a", "missing-b", {})
        assert comp.a.sessions == 0
        assert comp.b.sessions == 0
        assert comp.a.cost_per_call == Decimal(0)
