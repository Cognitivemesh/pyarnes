"""Tests for :mod:`pyarnes_bench.race`."""

from __future__ import annotations

import json

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from pyarnes_bench import (
    RaceCriterion,
    RaceDimension,
    RaceEvaluator,
    RaceScore,
    RaceWeights,
)
from pyarnes_core.errors import LLMRecoverableError, UserFixableError


class ScriptedJudge:
    """Deterministic judge driven by explicit per-prompt branches.

    ``score_fn(prompt) -> float`` lets tests vary scoring behaviour
    while the weighting / criteria responses remain fixed.
    """

    def __init__(
        self,
        *,
        weights: dict[str, float] | None = None,
        score_fn: object = None,
        criteria_per_dimension: int = 2,
    ) -> None:
        self._weights = weights or {
            "comprehensiveness": 0.25,
            "depth": 0.25,
            "instruction_following": 0.25,
            "readability": 0.25,
        }
        self._score_fn = score_fn or (lambda prompt: 0.5)
        self._k = criteria_per_dimension
        self.calls = 0

    async def judge(self, prompt: str) -> str:
        self.calls += 1
        if "importance weights" in prompt:
            return json.dumps({"weights": self._weights})
        if "sub-criteria" in prompt:
            dim = self._dimension_from_prompt(prompt)
            equal = 1.0 / self._k
            return json.dumps(
                {"criteria": [{"dimension": dim, "text": f"{dim}_c{i}", "weight": equal} for i in range(self._k)]}
            )
        if "Rate the report" in prompt:
            return json.dumps({"score": self._score_fn(prompt), "reason": "ok"})
        raise RuntimeError(f"unexpected prompt: {prompt[:80]}")

    @staticmethod
    def _dimension_from_prompt(prompt: str) -> str:
        for d in ("comprehensiveness", "depth", "instruction_following", "readability"):
            if f'"{d}"' in prompt:
                return d
        raise AssertionError("no dimension in prompt")


class TestRaceWeights:
    def test_sum_to_one(self) -> None:
        w = RaceWeights(weights=dict.fromkeys(RaceDimension, 0.25))
        assert sum(w.weights.values()) == pytest.approx(1.0)

    def test_renormalizes_minor_drift(self) -> None:
        w = RaceWeights(
            weights={
                RaceDimension.COMPREHENSIVENESS: 0.26,
                RaceDimension.DEPTH: 0.24,
                RaceDimension.INSTRUCTION_FOLLOWING: 0.25,
                RaceDimension.READABILITY: 0.25,
            }
        )
        assert sum(w.weights.values()) == pytest.approx(1.0)

    def test_rejects_below_floor(self) -> None:
        with pytest.raises(ValidationError):
            RaceWeights(weights=dict.fromkeys(RaceDimension, 0.0))

    def test_rejects_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            RaceWeights(weights={RaceDimension.DEPTH: 1.5, RaceDimension.COMPREHENSIVENESS: 0.0})


class TestRaceEvaluator:
    @pytest.mark.asyncio
    async def test_target_equals_reference_is_half(self) -> None:
        judge = ScriptedJudge(score_fn=lambda p: 0.6)
        evaluator = RaceEvaluator(client=judge, trials=1)
        score = await evaluator.evaluate(
            task_prompt="task",
            target_report="same",
            reference_report="same",
        )
        assert score.final_score == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_target_better_than_reference(self) -> None:
        def scorer(prompt: str) -> float:
            return 0.9 if "TARGETX" in prompt else 0.3

        judge = ScriptedJudge(score_fn=scorer)
        evaluator = RaceEvaluator(client=judge, trials=1)
        score = await evaluator.evaluate(
            task_prompt="task",
            target_report="TARGETX report content",
            reference_report="other baseline content",
        )
        assert score.final_score > 0.5
        assert 0.0 <= score.final_score <= 1.0

    @pytest.mark.asyncio
    async def test_criteria_per_dimension_normalize_to_one(self) -> None:
        judge = ScriptedJudge(criteria_per_dimension=3)
        evaluator = RaceEvaluator(client=judge, trials=1)
        score = await evaluator.evaluate(
            task_prompt="task",
            target_report="t",
            reference_report="r",
        )
        for dimension in RaceDimension:
            weights = [c.weight for c in score.criteria if c.dimension == dimension]
            assert sum(weights) == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_final_score_bounded(self) -> None:
        judge = ScriptedJudge(score_fn=lambda p: 1.0)
        evaluator = RaceEvaluator(client=judge, trials=1)
        score = await evaluator.evaluate(task_prompt="t", target_report="a", reference_report="b")
        assert 0.0 <= score.final_score <= 1.0

    @pytest.mark.asyncio
    async def test_to_eval_result_threshold(self) -> None:
        judge = ScriptedJudge(score_fn=lambda p: 0.8 if "target" in p.lower() else 0.2)
        evaluator = RaceEvaluator(client=judge, trials=1)
        score = await evaluator.evaluate(
            task_prompt="t",
            target_report="target stuff",
            reference_report="baseline",
        )
        eval_result = score.to_eval_result(scenario="demo", threshold=0.5)
        assert eval_result.scenario == "demo"
        assert eval_result.passed is (score.final_score >= 0.5)
        assert eval_result.score == score.final_score

    @pytest.mark.asyncio
    async def test_empty_target_raises(self) -> None:
        judge = ScriptedJudge()
        evaluator = RaceEvaluator(client=judge, trials=1)
        with pytest.raises(UserFixableError):
            await evaluator.evaluate(task_prompt="t", target_report="", reference_report="r")

    @pytest.mark.asyncio
    async def test_empty_reference_raises(self) -> None:
        judge = ScriptedJudge()
        evaluator = RaceEvaluator(client=judge, trials=1)
        with pytest.raises(UserFixableError):
            await evaluator.evaluate(task_prompt="t", target_report="x", reference_report="")

    @pytest.mark.asyncio
    async def test_malformed_json_raises_llm_recoverable(self) -> None:
        class BadJudge:
            async def judge(self, prompt: str) -> str:
                return "not json"

        evaluator = RaceEvaluator(client=BadJudge(), trials=1)
        with pytest.raises(LLMRecoverableError):
            await evaluator.evaluate(task_prompt="t", target_report="a", reference_report="b")

    def test_trials_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="trials"):
            RaceEvaluator(client=ScriptedJudge(), trials=0)


class TestRaceScoreAlignment:
    def test_score_arrays_must_align(self) -> None:
        criteria = (RaceCriterion(dimension=RaceDimension.DEPTH, text="c1", weight=1.0),)
        with pytest.raises(ValidationError):
            RaceScore(
                weights=RaceWeights(weights=dict.fromkeys(RaceDimension, 0.25)),
                criteria=criteria,
                per_criterion_target=(0.5, 0.6),
                per_criterion_reference=(0.5,),
                internal_target=0.5,
                internal_reference=0.5,
                final_score=0.5,
            )


class TestHypothesisInvariants:
    @given(
        target_score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        ref_score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    )
    @settings(max_examples=500, deadline=None)
    @pytest.mark.asyncio
    async def test_final_score_always_bounded(self, target_score: float, ref_score: float) -> None:
        def scorer(prompt: str) -> float:
            return target_score if "TGT_MARK" in prompt else ref_score

        judge = ScriptedJudge(score_fn=scorer)
        evaluator = RaceEvaluator(client=judge, trials=1)
        score = await evaluator.evaluate(
            task_prompt="t",
            target_report="TGT_MARK body",
            reference_report="baseline body",
        )
        assert 0.0 <= score.final_score <= 1.0

    @given(
        ref_score=st.floats(min_value=0.0, max_value=0.99, allow_nan=False),
    )
    @settings(max_examples=200, deadline=None)
    @pytest.mark.asyncio
    async def test_perfect_target_always_beats_reference(self, ref_score: float) -> None:
        """When target scores 1.0 and reference < 1.0, final_score must be > 0.5."""

        def scorer(prompt: str) -> float:
            return 1.0 if "TGT_MARK" in prompt else ref_score

        judge = ScriptedJudge(score_fn=scorer)
        evaluator = RaceEvaluator(client=judge, trials=1)
        score = await evaluator.evaluate(
            task_prompt="t",
            target_report="TGT_MARK body",
            reference_report="baseline body",
        )
        assert score.final_score > 0.5

    @given(score_a=st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    @settings(max_examples=300, deadline=None)
    @pytest.mark.asyncio
    async def test_equal_scores_always_yield_half(self, score_a: float) -> None:
        """When both target and reference are judged identically, final_score == 0.5."""

        def scorer(prompt: str) -> float:
            return score_a  # both sides receive the same score

        judge = ScriptedJudge(score_fn=scorer)
        evaluator = RaceEvaluator(client=judge, trials=1)
        score = await evaluator.evaluate(
            task_prompt="t",
            target_report="TGT body",
            reference_report="REF body",
        )
        assert score.final_score == pytest.approx(0.5)
