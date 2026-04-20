"""Tests for bench.eval — suite aggregation + quantify semantics."""

from __future__ import annotations

from pyarnes_bench.eval import EvalResult, EvalSuite


def _result(scenario: str, *, passed: bool) -> EvalResult:
    return EvalResult(
        scenario=scenario,
        expected="x",
        actual="x" if passed else "y",
        score=1.0 if passed else 0.0,
        passed=passed,
    )


class TestEvalSuite:
    """EvalSuite aggregates via more_itertools.quantify, preserving old semantics."""

    def test_pass_rate_empty(self) -> None:
        assert EvalSuite().pass_rate == 0.0

    def test_pass_rate_mixed(self) -> None:
        suite = EvalSuite()
        suite.add(_result("a", passed=True))
        suite.add(_result("b", passed=False))
        suite.add(_result("c", passed=True))
        assert suite.pass_rate == 2 / 3

    def test_summary_counts_match_sum_for_cond_idiom(self) -> None:
        """quantify(results, pred=is_passed) must equal sum(1 for r if r.passed)."""
        suite = EvalSuite(name="regression")
        for i in range(7):
            suite.add(_result(f"s{i}", passed=(i % 2 == 0)))
        summary = suite.summary()
        expected_passed = sum(1 for r in suite.results if r.passed)
        expected_failed = sum(1 for r in suite.results if not r.passed)
        assert summary["passed"] == expected_passed
        assert summary["failed"] == expected_failed
        assert summary["total"] == expected_passed + expected_failed

    def test_summary_failed_derived_from_total(self) -> None:
        """passed + failed == total (no double-scan)."""
        suite = EvalSuite()
        for i in range(4):
            suite.add(_result(f"s{i}", passed=bool(i % 2)))
        s = suite.summary()
        assert s["passed"] + s["failed"] == s["total"] == 4

    def test_average_score_empty(self) -> None:
        assert EvalSuite().average_score == 0.0

    def test_average_score_mean(self) -> None:
        suite = EvalSuite()
        suite.add(_result("a", passed=True))
        suite.add(_result("b", passed=False))
        assert suite.average_score == 0.5
