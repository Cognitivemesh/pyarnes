"""Scoring protocol and built-in scorers for evaluations."""

from __future__ import annotations

import asyncio
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal

from pyarnes_core.types import JudgeClient

__all__ = [
    "AsyncScorer",
    "CodeQualityScorer",
    "ExactMatchScorer",
    "LLMJudgeScorer",
    "Scorer",
    "_parse_score",
]


class Scorer(ABC):
    """Abstract base for synchronous evaluation scorers.

    Subclass and implement :meth:`score` to create custom scoring logic.
    The scenario/metadata keyword arguments let a single ``Scorer``
    dispatch per-scenario (exact-match vs regex vs LLM-judged) without
    every adopter having to fork the class.

    For scorers that require async I/O (e.g. LLM judge calls), use
    :class:`AsyncScorer` instead.
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


class AsyncScorer(ABC):
    """Abstract base for async evaluation scorers (e.g. LLM-as-judge).

    Parallel to :class:`Scorer` but with an ``async def score`` signature.
    Use this when the scoring implementation must ``await`` an external
    call such as an LLM judge.
    """

    @abstractmethod
    async def score(
        self,
        expected: Any,
        actual: Any,
        *,
        scenario: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> float:
        """Compute a score between 0.0 and 1.0 asynchronously.

        Args:
            expected: The reference / gold answer.
            actual: The agent's actual output.
            scenario: Optional scenario identifier.
            metadata: Optional free-form dict.

        Returns:
            A float in [0.0, 1.0].
        """


# ── LLM-as-judge scorers ──────────────────────────────────────────────────


def _parse_score(response: str) -> float:
    """Extract a float in [0.0, 1.0] from a judge response.

    Looks for the first bare number matching 0.x or 1.0 in the response.
    Returns 0.0 (conservative) if no valid score is found.
    """
    matches = re.findall(r"\b(0(?:\.\d+)?|1(?:\.0+)?)\b", response.strip())
    return float(matches[0]) if matches else 0.0


@dataclass(frozen=True, slots=True)
class LLMJudgeScorer(AsyncScorer):
    """LLM-as-judge scorer for open-ended and semantic evaluation.

    Uses a ``JudgeClient`` (not ``ModelClient`` — the judge needs a
    plain-text prompt interface, not tool-call dispatch). Based on the
    MT-Bench methodology: the judge scores the output on a rubric and
    returns a numeric grade.

    Attributes:
        judge: Async judge client.
        rubric: Evaluation criteria shown to the judge.
        grading_mode: ``"single"`` grades absolute quality;
            ``"reference_guided"`` grades relative to an expected answer.
    """

    judge: JudgeClient
    rubric: tuple[str, ...]
    grading_mode: Literal["single", "reference_guided"] = "single"

    async def score(
        self,
        expected: Any,
        actual: Any,
        *,
        scenario: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> float:
        """Grade ``actual`` using the LLM judge; return a score in [0.0, 1.0]."""
        del metadata
        prompt = self._build_prompt(expected, actual, scenario)
        response = await self.judge.judge(prompt)
        return _parse_score(response)

    def _build_prompt(self, expected: Any, actual: Any, scenario: str | None) -> str:
        rubric_text = "\n".join(f"{i + 1}. {r}" for i, r in enumerate(self.rubric))
        ref_section = f"Reference answer:\n{expected}\n\n" if self.grading_mode == "reference_guided" else ""
        return (
            f"You are an expert evaluator.\n\n"
            f"Task: {scenario or 'Evaluate the following output'}\n\n"
            f"{ref_section}"
            f"Output to grade:\n{actual}\n\n"
            f"Evaluation rubric:\n{rubric_text}\n\n"
            f"Grade on a scale of 0.0 (completely wrong) to 1.0 (perfect).\n"
            f"Respond with ONLY a number."
        )


@dataclass(frozen=True, slots=True)
class CodeQualityScorer(AsyncScorer):
    """Multi-dimension code quality scorer using an LLM judge.

    Each dimension is scored 0.0-1.0 and combined as a weighted average.
    Weights are stored as an immutable tuple of ``(dimension, weight)`` pairs
    to remain compatible with ``frozen=True``.

    Attributes:
        judge: Async judge client.
        dimension_weights: Ordered ``(dimension_name, weight)`` pairs.
            Weights need not sum to 1.0 — they are normalised internally.
    """

    judge: JudgeClient
    dimension_weights: tuple[tuple[str, float], ...] = (
        ("correctness", 0.40),
        ("style", 0.15),
        ("efficiency", 0.15),
        ("safety", 0.20),
        ("testability", 0.10),
    )

    async def score(
        self,
        expected: Any,
        actual: Any,
        *,
        scenario: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> float:
        """Score code quality as a weighted average across all dimensions."""
        del metadata
        total_weight = sum(w for _, w in self.dimension_weights)
        dim_scores = await asyncio.gather(
            *(self._score_dimension(dim, expected, actual, scenario) for dim, _ in self.dimension_weights)
        )
        weighted_sum = sum(s * w for s, (_, w) in zip(dim_scores, self.dimension_weights, strict=True))
        return weighted_sum / total_weight

    async def _score_dimension(self, dimension: str, expected: Any, actual: Any, scenario: str | None) -> float:
        prompt = (
            f"Evaluate the following code on the dimension: **{dimension}**\n\n"
            f"Task: {scenario or 'General code evaluation'}\n\n"
            f"Code to evaluate:\n{actual}\n\n"
            f"Reference solution:\n{expected}\n\n"
            f"Rate {dimension} from 0.0 (worst) to 1.0 (best). "
            f"Respond with ONLY a number."
        )
        response = await self.judge.judge(prompt)
        return _parse_score(response)
