"""Tests for LLMJudgeScorer, CodeQualityScorer, and _parse_score."""

from __future__ import annotations

import pytest

from pyarnes_bench.scorer import CodeQualityScorer, LLMJudgeScorer, _parse_score

# ── Helpers ────────────────────────────────────────────────────────────────


class FakeJudge:
    """Stub JudgeClient that returns a fixed response."""

    def __init__(self, response: str) -> None:
        self._response = response

    async def judge(self, prompt: str) -> str:
        return self._response


# ── _parse_score ───────────────────────────────────────────────────────────


class TestParseScore:
    def test_decimal(self) -> None:
        assert _parse_score("0.85") == 0.85

    def test_one(self) -> None:
        assert _parse_score("1.0") == 1.0

    def test_zero(self) -> None:
        assert _parse_score("0.0") == 0.0

    def test_zero_no_decimal(self) -> None:
        assert _parse_score("0") == 0.0

    def test_embedded_in_text(self) -> None:
        assert _parse_score("The score is 0.75 out of 1.0") == 0.75

    def test_no_number_returns_zero(self) -> None:
        assert _parse_score("no score here") == 0.0

    def test_out_of_range_number_not_matched(self) -> None:
        assert _parse_score("2.5 is too high") == 0.0


# ── LLMJudgeScorer ────────────────────────────────────────────────────────


class TestLLMJudgeScorer:
    @pytest.mark.asyncio
    async def test_score_single_mode(self) -> None:
        scorer = LLMJudgeScorer(
            judge=FakeJudge("0.8"),
            rubric=("correctness",),
        )
        result = await scorer.score("expected", "actual", scenario="test")
        assert result == 0.8

    @pytest.mark.asyncio
    async def test_score_reference_guided_mode(self) -> None:
        scorer = LLMJudgeScorer(
            judge=FakeJudge("0.9"),
            rubric=("matches reference",),
            grading_mode="reference_guided",
        )
        result = await scorer.score("ref answer", "agent answer")
        assert result == 0.9

    @pytest.mark.asyncio
    async def test_malformed_response_returns_zero(self) -> None:
        scorer = LLMJudgeScorer(
            judge=FakeJudge("I cannot determine a score"),
            rubric=("correctness",),
        )
        result = await scorer.score("expected", "actual")
        assert result == 0.0


# ── CodeQualityScorer ─────────────────────────────────────────────────────


class TestCodeQualityScorer:
    @pytest.mark.asyncio
    async def test_weighted_average(self) -> None:
        scorer = CodeQualityScorer(
            judge=FakeJudge("1.0"),
            dimension_weights=(
                ("correctness", 0.5),
                ("style", 0.5),
            ),
        )
        result = await scorer.score("expected", "actual")
        assert result == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_unequal_weights_normalised(self) -> None:
        responses = iter(["1.0", "0.0"])

        class SequentialJudge:
            async def judge(self, prompt: str) -> str:
                return next(responses)

        scorer = CodeQualityScorer(
            judge=SequentialJudge(),
            dimension_weights=(
                ("correctness", 0.8),
                ("style", 0.2),
            ),
        )
        result = await scorer.score("expected", "actual")
        # correctness=1.0 * 0.8 + style=0.0 * 0.2 / 1.0 = 0.8
        assert result == pytest.approx(0.8)

    @pytest.mark.asyncio
    async def test_default_dimensions_used(self) -> None:
        scorer = CodeQualityScorer(judge=FakeJudge("0.5"))
        result = await scorer.score("exp", "act")
        assert 0.0 <= result <= 1.0
