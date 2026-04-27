"""Tests for pyarnes_bench.burn — token cost tracking.

All stubs, fixture helpers, and test data use agnostic placeholder names.
No real tool names, model identifiers, provider names, or currency codes
appear anywhere in this file.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from pyarnes_bench.burn.costing import LiteLLMCostCalculator
from pyarnes_bench.burn.provider import BurnTracker, JsonlProvider
from pyarnes_bench.burn.types import Cost, SessionBurn, SessionMetadata, TokenUsage
from pyarnes_bench.eval import EvalResult, EvalSuite


# ── Stubs ──────────────────────────────────────────────────────────────────


class _StubJsonlProvider(JsonlProvider):
    """Test double — parses entries where ``k == 't'`` (generic key)."""

    def __init__(self, tool: str = "tool-a", sessions: list[SessionBurn] | None = None) -> None:
        self._tool = tool
        self._sessions = sessions or []

    @property
    def tool_name(self) -> str:
        return self._tool

    @property
    def ai_provider_name(self) -> str:
        return "prov-a"

    @property
    def session_glob(self) -> str:
        return "*.jsonl"

    def is_model_turn(self, entry: dict[str, Any]) -> bool:
        return entry.get("k") == "t"

    def extract_usage(self, entry: dict[str, Any]) -> TokenUsage | None:
        u = entry.get("u")
        if not isinstance(u, dict):
            return None
        return TokenUsage(input_tokens=u.get("i", 0), output_tokens=u.get("o", 0))

    def extract_model_id(self, entry: dict[str, Any]) -> str:
        return entry.get("m", "")

    def extract_timestamp(self, entry: dict[str, Any]) -> str | None:
        return entry.get("ts")

    def infer_model_family(self, model_id: str) -> str:
        return model_id.split("-")[0] if model_id else ""

    def burn_report(self, base: Path) -> list[SessionBurn]:
        # Override template method to return canned sessions (no disk I/O in tests)
        return self._sessions


class _StubCostCalculator:
    """Returns a fixed Cost for any model; used to isolate pricing from tracking."""

    def __init__(self, amount: str = "0.10", currency: str = "XXX") -> None:
        self._cost = Cost(amount=Decimal(amount), currency=currency)

    def calculate(self, model_id: str, usage: TokenUsage) -> Cost | None:
        return self._cost


# ── Fixture helpers ─────────────────────────────────────────────────────────


def _usage(inp: int = 100, out: int = 50) -> TokenUsage:
    return TokenUsage(input_tokens=inp, output_tokens=out)


def _meta(tool: str = "tool-a") -> SessionMetadata:
    return SessionMetadata(tool=tool, ai_provider="prov-a", model_id="model-x-1", model_family="model")


def _session(*, tool: str = "tool-a", inp: int = 100, out: int = 50, cost: Cost | None = None) -> SessionBurn:
    return SessionBurn(
        session_id="sess-1",
        project="proj-a",
        metadata=_meta(tool),
        start_time="2026-01-01T00:00:00Z",
        end_time="2026-01-01T01:00:00Z",
        turns=1,
        usage=_usage(inp, out),
        cost=cost,
    )


def _write_jsonl(path: Path, entries: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")


# ── TokenUsage ──────────────────────────────────────────────────────────────


class TestTokenUsage:
    def test_add_sums_all_fields(self) -> None:
        a = TokenUsage(input_tokens=10, output_tokens=5, cache_creation_tokens=3, cache_read_tokens=2)
        b = TokenUsage(input_tokens=20, output_tokens=15, cache_creation_tokens=7, cache_read_tokens=8)
        result = a + b
        assert result.input_tokens == 30
        assert result.output_tokens == 20
        assert result.cache_creation_tokens == 10
        assert result.cache_read_tokens == 10

    def test_total_excludes_cache(self) -> None:
        u = TokenUsage(input_tokens=100, output_tokens=50, cache_creation_tokens=999, cache_read_tokens=999)
        assert u.total_tokens == 150

    def test_as_dict_includes_total(self) -> None:
        u = TokenUsage(input_tokens=10, output_tokens=5)
        d = u.as_dict()
        assert d["total_tokens"] == 15
        assert "cache_creation_tokens" in d


# ── Cost ────────────────────────────────────────────────────────────────────


class TestCost:
    def test_stores_currency_code(self) -> None:
        c = Cost(amount=Decimal("1.23"), currency="ZZZ")
        assert c.currency == "ZZZ"
        assert c.amount == Decimal("1.23")

    def test_as_dict_round_trips(self) -> None:
        c = Cost(amount=Decimal("0.05"), currency="AAA")
        d = c.as_dict()
        assert d["currency"] == "AAA"
        assert d["amount"] == "0.05"


# ── LiteLLMCostCalculator ───────────────────────────────────────────────────


class TestCostCalculator:
    def test_prices_known_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import litellm

        monkeypatch.setattr(
            litellm,
            "model_cost",
            {"stub-model": {"input_cost_per_token": 0.001, "output_cost_per_token": 0.002}},
        )
        calc = LiteLLMCostCalculator(currency="XXX")
        result = calc.calculate("stub-model", TokenUsage(input_tokens=100, output_tokens=50))
        assert result is not None
        assert result.currency == "XXX"
        # 100*0.001 + 50*0.002 = 0.1 + 0.1 = 0.2
        assert result.amount == Decimal("0.2")

    def test_returns_none_for_unknown_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import litellm

        monkeypatch.setattr(litellm, "model_cost", {})
        calc = LiteLLMCostCalculator()
        assert calc.calculate("unknown-model", _usage()) is None

    def test_cache_multipliers_applied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cache creation and read tokens use different multipliers."""
        import litellm

        monkeypatch.setattr(
            litellm,
            "model_cost",
            {"stub-model": {"input_cost_per_token": 1.0, "output_cost_per_token": 2.0}},
        )
        calc = LiteLLMCostCalculator(currency="XXX")
        usage = TokenUsage(
            input_tokens=0,
            output_tokens=0,
            cache_creation_tokens=10,  # 10 * 1.0 * 1.25 = 12.5
            cache_read_tokens=10,       # 10 * 1.0 * 0.10 = 1.0
        )
        result = calc.calculate("stub-model", usage)
        assert result is not None
        assert result.amount == Decimal("13.5")


# ── JsonlProvider / parse_session ──────────────────────────────────────────


class TestJsonlProvider:
    def test_builds_session_burn_from_file(self, tmp_path: Path) -> None:
        f = tmp_path / "s.jsonl"
        _write_jsonl(f, [
            {"k": "t", "u": {"i": 10, "o": 5}, "m": "fam-v1", "ts": "2026-01-01T00:00:00Z"},
            {"k": "t", "u": {"i": 20, "o": 10}, "m": "fam-v1", "ts": "2026-01-01T01:00:00Z"},
        ])
        provider = _StubJsonlProvider()
        result = provider.parse_session(f)
        assert result is not None
        assert result.turns == 2
        assert result.usage.input_tokens == 30
        assert result.usage.output_tokens == 15
        assert result.start_time == "2026-01-01T00:00:00Z"
        assert result.end_time == "2026-01-01T01:00:00Z"
        assert result.metadata.model_id == "fam-v1"
        assert result.metadata.model_family == "fam"

    def test_returns_none_for_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.jsonl"
        f.write_text("", encoding="utf-8")
        assert _StubJsonlProvider().parse_session(f) is None

    def test_returns_none_when_no_model_turns(self, tmp_path: Path) -> None:
        f = tmp_path / "other.jsonl"
        _write_jsonl(f, [{"k": "other", "data": 1}])
        assert _StubJsonlProvider().parse_session(f) is None

    def test_skips_malformed_json_lines(self, tmp_path: Path) -> None:
        f = tmp_path / "mixed.jsonl"
        f.write_text(
            '{"k":"t","u":{"i":5,"o":3},"m":"x"}\nnot-json\n{"k":"t","u":{"i":2,"o":1},"m":"x"}\n',
            encoding="utf-8",
        )
        result = _StubJsonlProvider().parse_session(f)
        assert result is not None
        assert result.turns == 2

    def test_glob_applied_to_base(self, tmp_path: Path) -> None:
        (tmp_path / "a.jsonl").write_text("", encoding="utf-8")
        (tmp_path / "b.jsonl").write_text("", encoding="utf-8")
        (tmp_path / "c.txt").write_text("", encoding="utf-8")
        paths = _StubJsonlProvider().discover_sessions(tmp_path)
        names = {p.name for p in paths}
        assert names == {"a.jsonl", "b.jsonl"}

    def test_project_derived_from_parent_dir(self, tmp_path: Path) -> None:
        sub = tmp_path / "my-project"
        sub.mkdir()
        f = sub / "sess.jsonl"
        _write_jsonl(f, [{"k": "t", "u": {"i": 1, "o": 1}, "m": "x"}])
        # Use a provider whose glob returns this file
        provider = _StubJsonlProvider()
        result = provider.parse_session(f)
        assert result is not None
        assert result.project == "my-project"


# ── BurnTracker ─────────────────────────────────────────────────────────────


class TestBurnTracker:
    def test_merges_two_providers(self) -> None:
        s1 = _session(tool="tool-a")
        s2 = _session(tool="tool-b")
        tracker = BurnTracker(
            _StubJsonlProvider("tool-a", [s1]),
            _StubJsonlProvider("tool-b", [s2]),
        )
        report = tracker.report()
        assert set(report) == {"tool-a", "tool-b"}
        assert len(report["tool-a"]) == 1
        assert len(report["tool-b"]) == 1

    def test_sums_usage_across_providers(self) -> None:
        s1 = _session(inp=100, out=50)
        s2 = _session(inp=200, out=100)
        tracker = BurnTracker(
            _StubJsonlProvider("tool-a", [s1]),
            _StubJsonlProvider("tool-b", [s2]),
        )
        usage = tracker.total_usage()
        assert usage.input_tokens == 300
        assert usage.output_tokens == 150

    def test_no_calculator_total_cost_is_none(self) -> None:
        tracker = BurnTracker(_StubJsonlProvider("tool-a", [_session()]))
        assert tracker.total_cost() is None

    def test_attaches_cost_from_calculator(self) -> None:
        calc = _StubCostCalculator(amount="0.05", currency="XXX")
        tracker = BurnTracker(_StubJsonlProvider("tool-a", [_session()]), calculator=calc)
        report = tracker.report()
        assert report["tool-a"][0].cost is not None
        assert report["tool-a"][0].cost.amount == Decimal("0.05")

    def test_total_cost_sums_same_currency(self) -> None:
        cost = Cost(Decimal("0.10"), "XXX")
        s1 = _session(cost=cost)
        s2 = _session(cost=cost)
        # Inject already-costed sessions via a calc that returns the same value
        calc = _StubCostCalculator("0.10", "XXX")
        tracker = BurnTracker(
            _StubJsonlProvider("tool-a", [s1]),
            _StubJsonlProvider("tool-b", [s2]),
            calculator=calc,
        )
        total = tracker.total_cost()
        assert total is not None
        assert total.amount == Decimal("0.20")
        assert total.currency == "XXX"

    def test_total_cost_mixed_currencies_is_none(self) -> None:
        s1 = _session(cost=Cost(Decimal("1"), "AAA"))
        s2 = _session(cost=Cost(Decimal("1"), "BBB"))
        # No calculator — pre-set costs on the sessions are preserved as-is,
        # so total_cost must return None because currencies differ.
        tracker = BurnTracker(
            _StubJsonlProvider("tool-a", [s1]),
            _StubJsonlProvider("tool-b", [s2]),
        )
        assert tracker.total_cost() is None

    def test_report_is_cached(self) -> None:
        provider = _StubJsonlProvider("tool-a", [_session()])
        tracker = BurnTracker(provider)
        first = tracker.report()
        second = tracker.report()
        assert first is second  # same object, not a second call


# ── EvalSuite token-burn integration ───────────────────────────────────────


class TestEvalSuiteTokenBurn:
    def _result(self, *, usage: TokenUsage | None = None, cost: Cost | None = None) -> EvalResult:
        return EvalResult(
            scenario="s",
            expected="x",
            actual="x",
            score=1.0,
            passed=True,
            usage=usage,
            cost=cost,
        )

    def test_total_usage_none_when_no_results_have_usage(self) -> None:
        suite = EvalSuite()
        suite.add(self._result())
        assert suite.total_usage is None

    def test_total_usage_sums_non_none(self) -> None:
        suite = EvalSuite()
        suite.add(self._result(usage=_usage(inp=10, out=5)))
        suite.add(self._result())  # no usage
        suite.add(self._result(usage=_usage(inp=20, out=10)))
        total = suite.total_usage
        assert total is not None
        assert total.input_tokens == 30
        assert total.output_tokens == 15

    def test_cost_efficiency_ratio(self) -> None:
        suite = EvalSuite()
        # score=1.0, cost=0.04  → efficiency = 1.0 / 0.04 * 100 = 2500.0
        suite.add(self._result(cost=Cost(Decimal("0.02"), "XXX")))
        suite.add(self._result(cost=Cost(Decimal("0.02"), "XXX")))
        eff = suite.cost_efficiency
        assert eff is not None
        assert abs(eff - 2500.0) < 0.01

    def test_cost_efficiency_none_without_costs(self) -> None:
        suite = EvalSuite()
        suite.add(self._result())
        assert suite.cost_efficiency is None

    def test_cost_efficiency_none_mixed_currencies(self) -> None:
        suite = EvalSuite()
        suite.add(self._result(cost=Cost(Decimal("1"), "AAA")))
        suite.add(self._result(cost=Cost(Decimal("1"), "BBB")))
        assert suite.cost_efficiency is None

    def test_summary_includes_usage_when_present(self) -> None:
        suite = EvalSuite()
        suite.add(self._result(usage=_usage(inp=10, out=5)))
        s = suite.summary()
        assert "total_usage" in s
        assert s["total_usage"]["input_tokens"] == 10

    def test_summary_omits_usage_when_absent(self) -> None:
        suite = EvalSuite()
        suite.add(self._result())
        s = suite.summary()
        assert "total_usage" not in s
