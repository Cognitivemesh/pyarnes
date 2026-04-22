"""RACE — Reference-based Adaptive Criteria-driven Evaluation.

Post-hoc, sequential evaluator for long-form research reports. Scores a
finished ``target_report`` against a finished ``reference_report`` across
four dynamically weighted dimensions (comprehensiveness, depth,
instruction following, readability) using an LLM-as-judge. The final
score is normalized against the reference:

``S_final = S_int(target) / (S_int(target) + S_int(reference))``

so identical target/reference → 0.5, target strictly better → >0.5.

The evaluator does **not** orchestrate any agent, fetch any URL, or
run judge calls concurrently. Every trial, dimension, and criterion is
handled in a plain ``for`` loop that ``await``s one judge call at a
time — matching the serial-by-design convention of
``packages/harness/src/pyarnes_harness/loop.py``.

Typical usage (from an adopter's ``pytest`` suite)::

    evaluator = RaceEvaluator(client=my_model_client, trials=3)
    score: RaceScore = await evaluator.evaluate(
        task_prompt="Write a report on supply-chain risk",
        target_report=target_text,
        reference_report=reference_text,
    )
    suite.add(score.to_eval_result(scenario="q1-supply-chain", threshold=0.5))
"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pyarnes_bench._citations import strip_markers
from pyarnes_bench._judge import judge_json
from pyarnes_bench.eval import EvalResult
from pyarnes_core.errors import UserFixableError
from pyarnes_core.observe.logger import get_logger
from pyarnes_core.types import ModelClient

__all__ = [
    "RaceCriterion",
    "RaceDimension",
    "RaceEvaluator",
    "RacePrompts",
    "RaceScore",
    "RaceWeights",
]

logger = get_logger(__name__)

_WEIGHT_SUM_TOLERANCE = 1e-6
_WEIGHT_RENORM_FLOOR = 1e-3


class RaceDimension(StrEnum):
    """The four RACE dimensions scored on every report."""

    COMPREHENSIVENESS = "comprehensiveness"
    DEPTH = "depth"
    INSTRUCTION_FOLLOWING = "instruction_following"
    READABILITY = "readability"


_UnitFloat = Annotated[float, Field(ge=0.0, le=1.0)]


class RaceWeights(BaseModel):
    """Per-dimension weights produced by the weighting judge.

    Weights sum to 1 ± ``_WEIGHT_SUM_TOLERANCE``; the post-validator
    re-normalizes when the judge's output drifts slightly. Field-level
    constraints (each weight in ``[0, 1]``) still run on the raw input.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    weights: dict[RaceDimension, _UnitFloat]

    @model_validator(mode="after")
    def _normalize_sum(self) -> RaceWeights:
        total = sum(self.weights.values())
        if total < _WEIGHT_RENORM_FLOOR:
            raise ValueError(f"RaceWeights sum {total} below floor {_WEIGHT_RENORM_FLOOR}")
        if math.isclose(total, 1.0, abs_tol=_WEIGHT_SUM_TOLERANCE):
            return self
        return self.model_copy(
            update={"weights": {d: w / total for d, w in self.weights.items()}}
        )


class RaceCriterion(BaseModel):
    """One task-specific sub-criterion under a RACE dimension.

    Criteria weights within the same dimension sum to 1.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    dimension: RaceDimension
    text: str = Field(min_length=1)
    weight: _UnitFloat


_DEFAULT_WEIGHTING_PROMPT = (
    "You are assigning importance weights to four evaluation dimensions "
    "for the task below. Output ONLY a JSON object matching the schema "
    '{{"weights": {{"comprehensiveness": float, "depth": float, '
    '"instruction_following": float, "readability": float}}}} where the '
    "four floats are in [0, 1] and sum to 1.\n\nTask:\n{task_prompt}\n"
)
_DEFAULT_CRITERIA_PROMPT = (
    "You are deriving task-specific sub-criteria for the RACE dimension "
    '"{dimension}". Output ONLY a JSON object matching '
    '{{"criteria": [{{"dimension": "{dimension}", "text": str, '
    '"weight": float}}, ...]}} where weights are in [0, 1] and sum to 1. '
    "Return 3 to 5 criteria.\n\nTask:\n{task_prompt}\n"
)
_DEFAULT_SCORING_PROMPT = (
    "Rate the report below against the criterion, on a 0.0-1.0 scale. "
    "Output ONLY a JSON object matching "
    '{{"score": float, "reason": str}} with score in [0, 1].\n\n'
    "Dimension: {dimension}\nCriterion: {criterion}\n\n"
    "Report:\n{report}\n"
)


class RacePrompts(BaseModel):
    """Prompt templates used by the three judge calls.

    Every field has a sensible default; adopters override individual
    fields via constructor kwargs. The defaults are plain ``str`` with
    named placeholders (``{task_prompt}``, ``{dimension}``,
    ``{criterion}``, ``{report}``). Literal braces in the JSON-schema
    hints are escaped as ``{{`` / ``}}`` so ``str.format`` passes them
    through verbatim.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    weighting_prompt: str = _DEFAULT_WEIGHTING_PROMPT
    criteria_prompt: str = _DEFAULT_CRITERIA_PROMPT
    scoring_prompt: str = _DEFAULT_SCORING_PROMPT


class RaceScore(BaseModel):
    """Immutable result of a RACE evaluation.

    ``final_score`` is the reference-normalized score in ``[0, 1]``;
    ``per_criterion_*`` preserves the raw criterion-level scores so
    adopters can drill into which dimensions drove the verdict.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    weights: RaceWeights
    criteria: tuple[RaceCriterion, ...]
    per_criterion_target: tuple[_UnitFloat, ...]
    per_criterion_reference: tuple[_UnitFloat, ...]
    internal_target: _UnitFloat
    internal_reference: _UnitFloat
    final_score: _UnitFloat
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_alignment(self) -> RaceScore:
        n = len(self.criteria)
        if len(self.per_criterion_target) != n or len(self.per_criterion_reference) != n:
            raise ValueError("per-criterion score arrays must align with criteria")
        return self

    def to_eval_result(self, *, scenario: str, threshold: float = 0.5) -> EvalResult:
        """Adapt to :class:`pyarnes_bench.EvalResult` for ``EvalSuite``."""
        return EvalResult(
            scenario=scenario,
            expected=f"final_score >= {threshold}",
            actual=f"final_score = {self.final_score:.4f}",
            score=self.final_score,
            passed=self.final_score >= threshold,
            metadata={
                **self.metadata,
                "internal_target": self.internal_target,
                "internal_reference": self.internal_reference,
                "weights": {d.value: w for d, w in self.weights.weights.items()},
            },
        )


# ── internal judge-response DTOs (private) ─────────────────────────────────


class _WeightsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    weights: dict[RaceDimension, _UnitFloat]


class _CriteriaResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    criteria: list[RaceCriterion]


class _ScoreResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    score: _UnitFloat
    reason: str = ""


# ── evaluator ─────────────────────────────────────────────────────────────


class RaceEvaluator:
    """Post-hoc, sequential RACE evaluator.

    Args:
        client: Any ``ModelClient``; the judge.
        prompts: Overridable prompt templates; default
            :class:`RacePrompts` covers the zero-config path.
        trials: Number of weighting-judge trials to average; paper uses
            ≥3 to dampen LLM variance.
        dimensions: Subset of :class:`RaceDimension` to evaluate. Default
            is all four; narrow at your own risk (final-score semantics
            still hold, but the comparison to the paper breaks).
    """

    def __init__(
        self,
        client: ModelClient,
        *,
        prompts: RacePrompts | None = None,
        trials: int = 3,
        dimensions: tuple[RaceDimension, ...] = tuple(RaceDimension),
    ) -> None:
        """Configure the evaluator; see class docstring for semantics."""
        if trials < 1:
            raise ValueError("trials must be >= 1")
        if not dimensions:
            raise ValueError("at least one dimension required")
        self._client = client
        self._prompts = prompts or RacePrompts()
        self._trials = trials
        self._dimensions = dimensions

    async def evaluate(
        self,
        *,
        task_prompt: str,
        target_report: str,
        reference_report: str,
    ) -> RaceScore:
        """Run the full RACE pipeline end-to-end.

        Args:
            task_prompt: The original task description given to the agent.
            target_report: The report to be scored.
            reference_report: The anchor report used for normalization.

        Returns:
            A populated :class:`RaceScore`.

        Raises:
            UserFixableError: If any of the three inputs is blank.
            LLMRecoverableError: If the judge persistently returns
                non-JSON or fails Pydantic validation.
        """
        if not task_prompt.strip():
            raise UserFixableError(
                message="RACE evaluator requires a non-empty task_prompt",
                prompt_hint="Provide the original task description.",
            )
        if not target_report.strip():
            raise UserFixableError(
                message="RACE evaluator requires a non-empty target_report",
                prompt_hint="Provide the report to be scored.",
            )
        if not reference_report.strip():
            raise UserFixableError(
                message="RACE evaluator requires a non-empty reference_report",
                prompt_hint="Provide the reference report used for normalization.",
            )

        target = strip_markers(target_report)
        reference = strip_markers(reference_report)

        weights = await self._judge_weights(task_prompt)
        logger.info(
            "race.weights weights={weights}",
            weights={d.value: round(w, 4) for d, w in weights.weights.items()},
        )

        criteria: list[RaceCriterion] = []
        for dimension in self._dimensions:
            criteria.extend(await self._judge_criteria(task_prompt, dimension))

        per_target: list[float] = []
        per_reference: list[float] = []
        for criterion in criteria:
            per_target.append(await self._judge_score(criterion, target))
            per_reference.append(await self._judge_score(criterion, reference))

        internal_target = self._aggregate(weights, criteria, per_target)
        internal_reference = self._aggregate(weights, criteria, per_reference)
        denom = internal_target + internal_reference
        final_score = 0.5 if denom == 0.0 else internal_target / denom

        return RaceScore(
            weights=weights,
            criteria=tuple(criteria),
            per_criterion_target=tuple(per_target),
            per_criterion_reference=tuple(per_reference),
            internal_target=internal_target,
            internal_reference=internal_reference,
            final_score=final_score,
            metadata={"trials": self._trials, "num_criteria": len(criteria)},
        )

    async def _judge_weights(self, task_prompt: str) -> RaceWeights:
        totals: dict[RaceDimension, float] = dict.fromkeys(self._dimensions, 0.0)
        prompt = self._prompts.weighting_prompt.format(task_prompt=task_prompt)
        for _ in range(self._trials):
            response = await judge_json(self._client, prompt, _WeightsResponse)
            for dimension in self._dimensions:
                totals[dimension] += response.weights.get(dimension, 0.0)
        averaged = {d: totals[d] / self._trials for d in self._dimensions}
        total = sum(averaged.values())
        normalized = {d: (w / total if total > 0 else 1 / len(self._dimensions)) for d, w in averaged.items()}
        return RaceWeights(weights=normalized)

    async def _judge_criteria(
        self,
        task_prompt: str,
        dimension: RaceDimension,
    ) -> list[RaceCriterion]:
        prompt = self._prompts.criteria_prompt.format(
            task_prompt=task_prompt,
            dimension=dimension.value,
        )
        response = await judge_json(self._client, prompt, _CriteriaResponse)
        raw = [c for c in response.criteria if c.dimension == dimension]
        if not raw:
            raise UserFixableError(
                message=f"judge returned no criteria for dimension {dimension.value}",
                prompt_hint="Check the criteria prompt template for this dimension.",
            )
        total = sum(c.weight for c in raw)
        if total <= 0:
            raise UserFixableError(
                message=f"criteria for {dimension.value} have non-positive weight sum",
                prompt_hint="Check the criteria prompt template.",
            )
        return [
            RaceCriterion(dimension=c.dimension, text=c.text, weight=c.weight / total)
            for c in raw
        ]

    async def _judge_score(self, criterion: RaceCriterion, report: str) -> float:
        prompt = self._prompts.scoring_prompt.format(
            dimension=criterion.dimension.value,
            criterion=criterion.text,
            report=report,
        )
        response = await judge_json(self._client, prompt, _ScoreResponse)
        return response.score

    @staticmethod
    def _aggregate(
        weights: RaceWeights,
        criteria: list[RaceCriterion],
        scores: list[float],
    ) -> float:
        total = 0.0
        for criterion, score in zip(criteria, scores, strict=True):
            total += weights.weights[criterion.dimension] * criterion.weight * score
        return max(0.0, min(1.0, total))
