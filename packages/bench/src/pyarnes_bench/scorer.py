"""Scoring protocol and built-in scorers for evaluations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

__all__ = [
    "ExactMatchScorer",
    "Scorer",
]


class Scorer(ABC):
    """Abstract base for evaluation scorers.

    Subclass and implement :meth:`score` to create custom scoring logic.
    The scenario/metadata keyword arguments let a single ``Scorer``
    dispatch per-scenario (exact-match vs regex vs LLM-judged) without
    every adopter having to fork the class.
    """

    @abstractmethod
    def score(
        self,
        expected: Any,
        actual: Any,
        *,
        scenario: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> float:
        """Compute a score between 0.0 and 1.0.

        Args:
            expected: The reference / gold answer.
            actual: The agent's actual output.
            scenario: Optional scenario identifier so per-scenario logic
                (format checks vs factual QA vs open-ended) can branch
                on a single ``Scorer`` implementation.
            metadata: Optional free-form dict (e.g. rubric keys, weights).

        Returns:
            A float in [0.0, 1.0].
        """


@dataclass(frozen=True, slots=True)
class ExactMatchScorer(Scorer):
    """Score 1.0 if expected == actual, else 0.0.

    Attributes:
        case_sensitive: Whether string comparisons are case-sensitive.
    """

    case_sensitive: bool = True

    def score(
        self,
        expected: Any,
        actual: Any,
        *,
        scenario: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> float:
        """Return 1.0 on exact match, 0.0 otherwise."""
        del scenario, metadata  # unused by exact-match
        if isinstance(expected, str) and isinstance(actual, str) and not self.case_sensitive:
            return 1.0 if expected.lower() == actual.lower() else 0.0
        return 1.0 if expected == actual else 0.0
