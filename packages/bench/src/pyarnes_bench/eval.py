"""Evaluation runner — define and execute benchmark scenarios.

Token-aware extension: ``EvalResult`` carries optional ``usage`` and
``cost`` fields so token consumption becomes a first-class evaluation
axis alongside pass/fail score. ``EvalSuite`` aggregates these and
exposes a ``cost_efficiency`` property (score per unit cost).

Why ``usage`` and ``cost`` are separate: token counts are objective;
monetary cost depends on a pricing model that may be absent or need a
different currency. Keeping them separate avoids coupling to any one
calculator at the result level.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from functools import reduce
from operator import attrgetter
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pyarnes_bench.burn.types import Cost, TokenUsage

from more_itertools import quantify

from pyarnes_core.observability import log_event
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
        usage: Token counts for this run; ``None`` when not instrumented.
        cost: Monetary cost for this run; ``None`` when no calculator was
            used. Kept separate from ``usage`` because cost depends on a
            pricing model that may be absent or currency-specific.
    """

    scenario: str
    expected: Any
    actual: Any
    score: float
    passed: bool
    metadata: dict[str, Any] = field(default_factory=dict)
    # Optional token-burn fields — backward-compatible (default None)
    usage: TokenUsage | None = None
    cost: Cost | None = None

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict (suitable for JSONL logging)."""
        d: dict[str, Any] = {
            "scenario": self.scenario,
            "expected": str(self.expected),
            "actual": str(self.actual),
            "score": self.score,
            "passed": self.passed,
            "metadata": self.metadata,
        }
        if self.usage is not None:
            d["usage"] = self.usage.as_dict()
        if self.cost is not None:
            d["cost"] = self.cost.as_dict()
        return d


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
        log_event(
            logger,
            "eval.recorded",
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

    @property
    def total_usage(self) -> TokenUsage | None:
        """Sum ``TokenUsage`` across all results that carry one.

        Why on suite not result: efficiency is meaningful amortized across
        multiple runs; per-result cost is noise.

        Returns:
            Accumulated ``TokenUsage``, or ``None`` when no result has usage.
        """
        usages = [r.usage for r in self.results if r.usage is not None]
        if not usages:
            return None
        return reduce(lambda a, b: a + b, usages)

    @property
    def cost_efficiency(self) -> float | None:
        """Score per unit cost — ``average_score / total_cost.amount * 100``.

        Returns:
            Efficiency as score-points per 100 units of cost, or ``None``
            when no result carries a ``Cost`` or total cost is zero.
            Mixed-currency results return ``None`` (summation would mislead).
        """
        costs = [r.cost for r in self.results if r.cost is not None]
        if not costs:
            return None

        currencies = {c.currency for c in costs}
        if len(currencies) != 1:
            return None  # mixed currencies: summation would be misleading

        total_cost = sum((c.amount for c in costs), Decimal(0))
        if total_cost == 0:
            return None

        return float(Decimal(str(self.average_score)) / total_cost * 100)

    def summary(self) -> dict[str, Any]:
        """Return an aggregate summary dict."""
        total = len(self.results)
        passed = quantify(self.results, pred=_is_passed)
        d: dict[str, Any] = {
            "suite": self.name,
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": passed / total if total else 0.0,
            "average_score": self.average_score,
        }
        usage = self.total_usage
        if usage is not None:
            d["total_usage"] = usage.as_dict()
        efficiency = self.cost_efficiency
        if efficiency is not None:
            d["cost_efficiency"] = efficiency
        return d

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
