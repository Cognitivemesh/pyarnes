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
    """

    @abstractmethod
    def score(self, expected: Any, actual: Any) -> float:
        """Compute a score between 0.0 and 1.0.

        Args:
            expected: The reference / gold answer.
            actual: The agent's actual output.

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

    def score(self, expected: Any, actual: Any) -> float:
        """Return 1.0 on exact match, 0.0 otherwise."""
        if isinstance(expected, str) and isinstance(actual, str) and not self.case_sensitive:
            return 1.0 if expected.lower() == actual.lower() else 0.0
        return 1.0 if expected == actual else 0.0
