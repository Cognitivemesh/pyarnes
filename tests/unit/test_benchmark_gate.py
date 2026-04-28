"""Tests for BenchmarkGateGuardrail."""

from __future__ import annotations

import pytest

from pyarnes_core.errors import UserFixableError
from pyarnes_guardrails.benchmark_gate import BenchmarkGateGuardrail

# ── Fake suite ────────────────────────────────────────────────────────────────


class _Suite:
    def __init__(self, score: float) -> None:
        self._score = score

    @property
    def average_score(self) -> float:
        return self._score


def _factory(score: float):
    async def _f():
        return _Suite(score)

    return _f


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestBenchmarkGateGuardrail:
    async def test_passes_when_score_at_threshold(self) -> None:
        g = BenchmarkGateGuardrail(suite_factory=_factory(0.8), threshold=0.8)
        await g.check("mytool", {})  # should not raise

    async def test_passes_when_score_above_threshold(self) -> None:
        g = BenchmarkGateGuardrail(suite_factory=_factory(0.95), threshold=0.8)
        await g.check("mytool", {})

    async def test_raises_when_score_below_threshold(self) -> None:
        g = BenchmarkGateGuardrail(suite_factory=_factory(0.5), threshold=0.8)
        with pytest.raises(UserFixableError, match=r"0\.500"):
            await g.check("mytool", {})

    async def test_error_message_contains_tool_name(self) -> None:
        g = BenchmarkGateGuardrail(suite_factory=_factory(0.1), threshold=0.8)
        with pytest.raises(UserFixableError, match="execute_code"):
            await g.check("execute_code", {})

    async def test_default_threshold_is_0_8(self) -> None:
        g = BenchmarkGateGuardrail(suite_factory=_factory(0.0))
        assert g.threshold == 0.8

    async def test_default_gate_tools_is_empty(self) -> None:
        g = BenchmarkGateGuardrail(suite_factory=_factory(1.0))
        assert g.gate_tools == frozenset()

    async def test_gate_tools_empty_applies_to_all(self) -> None:
        g = BenchmarkGateGuardrail(suite_factory=_factory(0.1), threshold=0.8)
        with pytest.raises(UserFixableError):
            await g.check("any_tool", {})

    async def test_gate_tools_skips_unlisted_tool(self) -> None:
        g = BenchmarkGateGuardrail(
            suite_factory=_factory(0.1),
            threshold=0.8,
            gate_tools=frozenset({"restricted_tool"}),
        )
        await g.check("other_tool", {})  # not gated, should not raise

    async def test_gate_tools_enforces_listed_tool(self) -> None:
        g = BenchmarkGateGuardrail(
            suite_factory=_factory(0.1),
            threshold=0.8,
            gate_tools=frozenset({"restricted_tool"}),
        )
        with pytest.raises(UserFixableError):
            await g.check("restricted_tool", {})

    async def test_factory_called_each_check(self) -> None:
        call_count = 0

        async def _counting_factory():
            nonlocal call_count
            call_count += 1
            return _Suite(1.0)

        g = BenchmarkGateGuardrail(suite_factory=_counting_factory)
        await g.check("t", {})
        await g.check("t", {})
        assert call_count == 2

    async def test_exported_from_guardrails_package(self) -> None:
        from pyarnes_guardrails import BenchmarkGateGuardrail as Imported  # noqa: PLC0415

        assert Imported is BenchmarkGateGuardrail
