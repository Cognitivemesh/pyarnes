"""Tests for bench.scorer — widened signature accepts scenario context."""

from __future__ import annotations

from typing import Any

from pyarnes_bench.scorer import ExactMatchScorer, Scorer


class TestExactMatchScorer:
    """Positional-arg callers keep working; keyword args are accepted."""

    def test_basic_match(self) -> None:
        scorer = ExactMatchScorer()
        assert scorer.score("x", "x") == 1.0
        assert scorer.score("x", "y") == 0.0

    def test_case_insensitive(self) -> None:
        scorer = ExactMatchScorer(case_sensitive=False)
        assert scorer.score("ABC", "abc") == 1.0

    def test_scenario_kwarg_accepted(self) -> None:
        scorer = ExactMatchScorer()
        assert scorer.score("x", "x", scenario="qa") == 1.0

    def test_metadata_kwarg_accepted(self) -> None:
        scorer = ExactMatchScorer()
        assert scorer.score("x", "x", scenario="qa", metadata={"weight": 2}) == 1.0


class ScenarioAwareScorer(Scorer):
    """Fixture: one scorer dispatches on scenario name."""

    def score(
        self,
        expected: Any,
        actual: Any,
        *,
        scenario: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> float:
        del metadata
        if scenario == "qa":
            return 1.0 if expected == actual else 0.0
        if scenario == "code":
            return 1.0 if str(expected) in str(actual) else 0.0
        return 0.0


class TestScenarioAwareScorer:
    """A single Scorer can branch on scenario without forking."""

    def test_qa_scenario_exact(self) -> None:
        scorer = ScenarioAwareScorer()
        assert scorer.score("2", "2", scenario="qa") == 1.0
        assert scorer.score("2", "3", scenario="qa") == 0.0

    def test_code_scenario_contains(self) -> None:
        scorer = ScenarioAwareScorer()
        assert scorer.score("return x", "def f():\n  return x\n", scenario="code") == 1.0

    def test_unknown_scenario_default(self) -> None:
        scorer = ScenarioAwareScorer()
        assert scorer.score("x", "x") == 0.0
