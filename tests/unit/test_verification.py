"""Tests for VerificationLoop and VerificationResult."""

from __future__ import annotations

import pytest

from pyarnes_core.errors import LLMRecoverableError, UserFixableError
from pyarnes_guardrails.guardrails import AsyncGuardrail, GuardrailChain
from pyarnes_harness.verification import VerificationLoop, VerificationResult

# ── Helpers ───────────────────────────────────────────────────────────────


async def _always_pass(output: object) -> bool:
    return True


async def _always_fail(output: object) -> bool:
    return False


def _generate_seq(*values: object):
    """Return a generate callable that yields values in sequence."""
    it = iter(values)

    async def _gen() -> object:
        return next(it)

    return _gen


def _test_seq(*results: bool):
    """Return a test callable that yields True/False in sequence."""
    it = iter(results)

    async def _test(output: object) -> bool:
        _ = output
        return next(it)

    return _test


async def _score_above(output: object) -> float:
    _ = output
    return 1.0


async def _score_below(output: object) -> float:
    _ = output
    return 0.1


# ── Tests ─────────────────────────────────────────────────────────────────


class TestVerificationResult:
    """VerificationResult is a frozen dataclass."""

    def test_fields(self) -> None:
        r = VerificationResult(output="x", passed=True, fix_attempts=0, score=0.5)
        assert r.output == "x"
        assert r.passed is True
        assert r.fix_attempts == 0
        assert r.score == 0.5

    def test_immutable(self) -> None:
        r = VerificationResult(output="x", passed=True, fix_attempts=0, score=0.0)
        with pytest.raises(Exception):  # noqa: B017
            r.output = "y"  # type: ignore[misc]


class TestVerificationLoopHappyPath:
    """First attempt passes every gate."""

    @pytest.mark.asyncio()
    async def test_happy_path_no_benchmark(self) -> None:
        loop = VerificationLoop()
        result = await loop.run(
            task="test task",
            generate=_generate_seq("output"),
            test=_always_pass,
        )
        assert result.passed is True
        assert result.fix_attempts == 0
        assert result.score == 0.0
        assert result.output == "output"

    @pytest.mark.asyncio()
    async def test_happy_path_with_benchmark(self) -> None:
        loop = VerificationLoop()
        result = await loop.run(
            task="bench task",
            generate=_generate_seq("output"),
            test=_always_pass,
            benchmark=_score_above,
            benchmark_threshold=0.5,
        )
        assert result.passed is True
        assert result.fix_attempts == 0
        assert result.score == 1.0


class TestVerificationLoopRetry:
    """Gate failures trigger a retry, then pass."""

    @pytest.mark.asyncio()
    async def test_test_failure_then_pass(self) -> None:
        # First call fails, second passes.
        loop = VerificationLoop(max_fix_attempts=3)
        result = await loop.run(
            task="retry task",
            generate=_generate_seq("bad", "good"),
            test=_test_seq(False, True),
        )
        assert result.passed is True
        assert result.fix_attempts == 1
        assert result.output == "good"

    @pytest.mark.asyncio()
    async def test_benchmark_failure_then_pass(self) -> None:
        scores = iter([0.1, 0.9])

        async def _bench(output: object) -> float:
            _ = output
            return next(scores)

        loop = VerificationLoop(max_fix_attempts=3)
        result = await loop.run(
            task="bench retry",
            generate=_generate_seq("v1", "v2"),
            test=_always_pass,
            benchmark=_bench,
            benchmark_threshold=0.5,
        )
        assert result.passed is True
        assert result.fix_attempts == 1
        assert result.score == 0.9


class TestVerificationLoopEscalation:
    """Exhausting fix attempts raises UserFixableError."""

    @pytest.mark.asyncio()
    async def test_exceeds_max_fix_attempts_on_test(self) -> None:
        # max_fix_attempts=2 → 3 total generates, all fail
        loop = VerificationLoop(max_fix_attempts=2)
        with pytest.raises(UserFixableError, match="fix attempt"):
            await loop.run(
                task="always fails",
                generate=_generate_seq("a", "b", "c"),
                test=_always_fail,
            )

    @pytest.mark.asyncio()
    async def test_escalation_message_contains_task(self) -> None:
        loop = VerificationLoop(max_fix_attempts=1)
        with pytest.raises(UserFixableError) as exc_info:
            await loop.run(
                task="my-task",
                generate=_generate_seq("x", "y"),
                test=_always_fail,
            )
        assert "my-task" in str(exc_info.value)

    @pytest.mark.asyncio()
    async def test_benchmark_below_threshold_escalates(self) -> None:
        loop = VerificationLoop(max_fix_attempts=1)
        with pytest.raises(UserFixableError, match="benchmark"):
            await loop.run(
                task="bench fail",
                generate=_generate_seq("a", "b"),
                test=_always_pass,
                benchmark=_score_below,
                benchmark_threshold=0.5,
            )


class TestVerificationLoopGuardrails:
    """Guardrail behaviour."""

    @pytest.mark.asyncio()
    async def test_guardrail_user_fixable_propagates_immediately(self) -> None:
        """UserFixableError from guardrail is re-raised without consuming fix attempts."""

        class _BlockAll(AsyncGuardrail):
            async def check(self, tool_name: str, arguments: dict) -> None:
                raise UserFixableError(message="policy violation")

        chain = GuardrailChain(guardrails=[_BlockAll()])
        loop = VerificationLoop(guardrail_chain=chain, max_fix_attempts=3)

        call_count = 0

        async def _gen() -> str:
            nonlocal call_count
            call_count += 1
            return "output"

        with pytest.raises(UserFixableError, match="policy violation"):
            await loop.run(task="blocked task", generate=_gen, test=_always_pass)

        # Should not retry after a UserFixableError from the guardrail.
        assert call_count == 1

    @pytest.mark.asyncio()
    async def test_guardrail_llm_recoverable_counts_as_fix_attempt(self) -> None:
        """LLMRecoverableError from guardrail triggers a fix cycle."""

        attempts = 0

        class _BlockOnce(AsyncGuardrail):
            async def check(self, tool_name: str, arguments: dict) -> None:
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise LLMRecoverableError(message="blocked once")

        chain = GuardrailChain(guardrails=[_BlockOnce()])
        loop = VerificationLoop(guardrail_chain=chain, max_fix_attempts=3)

        result = await loop.run(
            task="recoverable",
            generate=_generate_seq("first", "second"),
            test=_always_pass,
        )
        assert result.passed is True
        assert result.fix_attempts == 1

    @pytest.mark.asyncio()
    async def test_no_guardrail_chain(self) -> None:
        """No guardrail_chain means GUARDRAIL_CHECK stage is skipped."""
        loop = VerificationLoop(guardrail_chain=None)
        result = await loop.run(
            task="no guard",
            generate=_generate_seq("ok"),
            test=_always_pass,
        )
        assert result.passed is True


class TestVerificationLoopNoBenchmark:
    """When no benchmark is provided, score is 0.0."""

    @pytest.mark.asyncio()
    async def test_score_zero_when_no_benchmark(self) -> None:
        loop = VerificationLoop()
        result = await loop.run(
            task="no bench",
            generate=_generate_seq("out"),
            test=_always_pass,
        )
        assert result.score == 0.0
