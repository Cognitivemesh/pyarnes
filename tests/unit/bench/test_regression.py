"""Tests for RegressionReport."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyarnes_bench.eval import EvalResult, EvalSuite
from pyarnes_bench.regression import RegressionReport


def _make_suite(name: str, results: list[tuple[str, bool, float]]) -> EvalSuite:
    suite = EvalSuite(name=name)
    for scenario, passed, score in results:
        suite.add(EvalResult(scenario=scenario, expected="", actual="", score=score, passed=passed))
    return suite


class TestRegressionReport:
    def test_no_regressions_or_improvements(self) -> None:
        baseline = _make_suite("v1", [("a", True, 1.0), ("b", False, 0.0)])
        current = _make_suite("v2", [("a", True, 1.0), ("b", False, 0.0)])
        report = RegressionReport(baseline, current, "v1", "v2")
        assert report.regressions == []
        assert report.improvements == []

    def test_detects_regressions(self) -> None:
        baseline = _make_suite("v1", [("a", True, 1.0), ("b", True, 1.0)])
        current = _make_suite("v2", [("a", True, 1.0), ("b", False, 0.0)])
        report = RegressionReport(baseline, current, "v1", "v2")
        assert report.regressions == ["b"]
        assert report.improvements == []

    def test_detects_improvements(self) -> None:
        baseline = _make_suite("v1", [("a", False, 0.0)])
        current = _make_suite("v2", [("a", True, 1.0)])
        report = RegressionReport(baseline, current, "v1", "v2")
        assert report.regressions == []
        assert report.improvements == ["a"]

    def test_score_delta(self) -> None:
        baseline = _make_suite("v1", [("a", True, 0.5)])
        current = _make_suite("v2", [("a", True, 0.8)])
        report = RegressionReport(baseline, current, "v1", "v2")
        assert report.score_delta == pytest.approx(0.3)

    def test_to_markdown_contains_key_fields(self) -> None:
        baseline = _make_suite("v1", [("a", True, 1.0)])
        current = _make_suite("v2", [("a", False, 0.0)])
        report = RegressionReport(baseline, current, "v1", "v2")
        md = report.to_markdown()
        assert "v1" in md
        assert "v2" in md
        assert "- a" in md
        assert "Regressions (1)" in md

    def test_to_markdown_no_regressions(self) -> None:
        baseline = _make_suite("v1", [])
        current = _make_suite("v2", [])
        report = RegressionReport(baseline, current, "v1", "v2")
        md = report.to_markdown()
        assert "None" in md


class TestEvalSuiteJsonRoundtrip:
    def test_roundtrip(self, tmp_path: Path) -> None:
        suite = _make_suite("test", [("scenario_a", True, 0.9), ("scenario_b", False, 0.2)])
        path = tmp_path / "suite.json"
        suite.to_json(path)
        restored = EvalSuite.from_json(path)
        assert restored.name == "test"
        assert len(restored) == 2
        assert restored.results[0].scenario == "scenario_a"
        assert restored.results[0].passed is True
        assert restored.results[0].score == pytest.approx(0.9)

    def test_from_json_empty_results(self, tmp_path: Path) -> None:
        suite = EvalSuite(name="empty")
        path = tmp_path / "empty.json"
        suite.to_json(path)
        restored = EvalSuite.from_json(path)
        assert len(restored) == 0
