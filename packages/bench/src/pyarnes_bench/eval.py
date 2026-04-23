"""Evaluation runner — define and execute benchmark scenarios."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from operator import attrgetter
from pathlib import Path
from typing import Any

from more_itertools import quantify

from pyarnes_core.observe.logger import get_logger

__all__ = [
    "EvalResult",
    "EvalSuite",
]

logger = get_logger(__name__)

_is_passed = attrgetter("passed")


@dataclass(frozen=True, slots=True)
class EvalResult:
    """Immutable record of a single evaluation run.

    Attributes:
        scenario: Name or identifier of the scenario.
        expected: The expected output.
        actual: The actual output produced by the agent.
        score: Numeric score (0.0 - 1.0).
        passed: Whether the evaluation passed.
        metadata: Arbitrary key-value data attached to the result.
    """

    scenario: str
    expected: Any
    actual: Any
    score: float
    passed: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict (suitable for JSONL logging)."""
        return {
            "scenario": self.scenario,
            "expected": str(self.expected),
            "actual": str(self.actual),
            "score": self.score,
            "passed": self.passed,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class EvalSuite:
    """Collect, run, and summarise evaluation scenarios.

    Attributes:
        name: Suite name for reporting.
        results: Accumulated evaluation results.
    """

    name: str = "default"
    results: list[EvalResult] = field(default_factory=list)

    def add(self, result: EvalResult) -> None:
        """Append an evaluation result.

        Args:
            result: The ``EvalResult`` to record.
        """
        self.results.append(result)
        logger.info(
            "eval.recorded scenario={scenario} score={score} passed={passed}",
            scenario=result.scenario,
            score=result.score,
            passed=result.passed,
        )

    @property
    def pass_rate(self) -> float:
        """Return the fraction of evaluations that passed (0.0 - 1.0)."""
        if not self.results:
            return 0.0
        return quantify(self.results, pred=_is_passed) / len(self.results)

    @property
    def average_score(self) -> float:
        """Return the mean score across all evaluations."""
        if not self.results:
            return 0.0
        return sum(r.score for r in self.results) / len(self.results)

    def summary(self) -> dict[str, Any]:
        """Return an aggregate summary dict."""
        total = len(self.results)
        passed = quantify(self.results, pred=_is_passed)
        return {
            "suite": self.name,
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": passed / total if total else 0.0,
            "average_score": self.average_score,
        }

    def to_json(self, path: Path) -> None:
        """Persist the suite as a JSON file for regression comparison.

        Args:
            path: Destination file path. Parent directories must exist.
        """
        payload = {
            "suite": self.name,
            "results": [r.as_dict() for r in self.results],
        }
        path.write_text(json.dumps(payload, indent=2, default=str))

    @classmethod
    def from_json(cls, path: Path) -> EvalSuite:
        """Restore a suite from a JSON file written by :meth:`to_json`.

        Only ``scenario``, ``score``, and ``passed`` are preserved —
        ``expected`` and ``actual`` are stored as strings and
        ``metadata`` defaults to ``{}``.

        Args:
            path: Path to a JSON file previously written by ``to_json``.
        """
        payload: dict[str, Any] = json.loads(path.read_text())
        suite = cls(name=payload.get("suite", "default"))
        for raw in payload.get("results", []):
            suite.results.append(
                EvalResult(
                    scenario=raw["scenario"],
                    expected=raw.get("expected", ""),
                    actual=raw.get("actual", ""),
                    score=float(raw["score"]),
                    passed=bool(raw["passed"]),
                    metadata=raw.get("metadata", {}),
                )
            )
        return suite

    def __len__(self) -> int:  # noqa: D105
        return len(self.results)

    def __repr__(self) -> str:  # noqa: D105
        return f"EvalSuite(name={self.name!r}, results={len(self.results)})"
