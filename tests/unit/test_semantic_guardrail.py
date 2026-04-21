"""Tests for SemanticGuardrail, AsyncGuardrail, and async GuardrailChain."""

from __future__ import annotations

import pytest

from pyarnes_core.errors import LLMRecoverableError, UserFixableError
from pyarnes_guardrails import (
    AsyncGuardrail,
    CommandGuardrail,
    GuardrailChain,
    PathGuardrail,
    SemanticGuardrail,
)
from pyarnes_guardrails.semantic import _extract_reasoning, _extract_score

# ── Helpers ────────────────────────────────────────────────────────────────


class FakeJudge:
    """Stub JudgeClient that returns a fixed response."""

    def __init__(self, response: str) -> None:
        self._response = response

    async def judge(self, prompt: str) -> str:
        return self._response

    # Verify it satisfies the JudgeClient protocol at runtime
    def __class_getitem__(cls, item):  # type: ignore[override]
        return cls


class ErrorJudge:
    """Stub JudgeClient that always raises."""

    async def judge(self, prompt: str) -> str:
        raise RuntimeError("judge unavailable")


# ── _extract_score / _extract_reasoning ───────────────────────────────────


class TestExtractScore:
    def test_valid_score(self) -> None:
        assert _extract_score("SCORE: 0.85\nREASONING: looks fine") == 0.85

    def test_score_one(self) -> None:
        assert _extract_score("SCORE: 1.0\nREASONING: perfect") == 1.0

    def test_score_zero(self) -> None:
        assert _extract_score("SCORE: 0.0\nREASONING: bad") == 0.0

    def test_no_score_line_returns_zero(self) -> None:
        assert _extract_score("no score here") == 0.0

    def test_malformed_float_returns_zero(self) -> None:
        assert _extract_score("SCORE: abc") == 0.0


class TestExtractReasoning:
    def test_present(self) -> None:
        assert _extract_reasoning("SCORE: 0.5\nREASONING: it is okay") == "it is okay"

    def test_missing(self) -> None:
        assert _extract_reasoning("SCORE: 0.5") == "No reasoning provided"


# ── SemanticGuardrail ──────────────────────────────────────────────────────


class TestSemanticGuardrail:
    @pytest.mark.asyncio
    async def test_passes_when_score_above_threshold(self) -> None:
        g = SemanticGuardrail(
            judge=FakeJudge("SCORE: 0.9\nREASONING: fine"),
            task_context="Write a Python file",
            threshold=0.7,
        )
        await g.check("write_file", {"path": "/workspace/x.py"})

    @pytest.mark.asyncio
    async def test_blocks_with_recoverable_error_by_default(self) -> None:
        g = SemanticGuardrail(
            judge=FakeJudge("SCORE: 0.3\nREASONING: dangerous"),
            task_context="Write a Python file",
            threshold=0.7,
        )
        with pytest.raises(LLMRecoverableError, match=r"0\.30"):
            await g.check("delete_all", {"path": "/"})

    @pytest.mark.asyncio
    async def test_blocks_with_user_fixable_when_requested(self) -> None:
        g = SemanticGuardrail(
            judge=FakeJudge("SCORE: 0.1\nREASONING: wrong"),
            task_context="Read files only",
            threshold=0.7,
            block_error="fixable",
        )
        with pytest.raises(UserFixableError):
            await g.check("delete_all", {})

    @pytest.mark.asyncio
    async def test_judge_failure_raises_recoverable_error(self) -> None:
        g = SemanticGuardrail(
            judge=ErrorJudge(),
            task_context="Any task",
            threshold=0.5,
        )
        with pytest.raises(LLMRecoverableError, match="judge failed"):
            await g.check("some_tool", {})

    @pytest.mark.asyncio
    async def test_score_exactly_at_threshold_passes(self) -> None:
        g = SemanticGuardrail(
            judge=FakeJudge("SCORE: 0.7\nREASONING: borderline"),
            task_context="Any task",
            threshold=0.7,
        )
        await g.check("read_file", {"path": "/workspace/a.py"})


# ── AsyncGuardrail is abstract ─────────────────────────────────────────────


class TestAsyncGuardrailABC:
    def test_cannot_instantiate_directly(self) -> None:
        with pytest.raises(TypeError):
            AsyncGuardrail()  # type: ignore[abstract]


# ── GuardrailChain (async) ─────────────────────────────────────────────────


class TestGuardrailChainAsync:
    @pytest.mark.asyncio
    async def test_sync_only_chain_still_works(self) -> None:
        chain = GuardrailChain(
            guardrails=[
                PathGuardrail(allowed_roots=("/workspace",)),
                CommandGuardrail(),
            ]
        )
        await chain.check("shell", {"command": "echo hi", "path": "/workspace/file.txt"})

    @pytest.mark.asyncio
    async def test_async_guardrail_in_chain_passes(self) -> None:
        chain = GuardrailChain(
            guardrails=[
                PathGuardrail(allowed_roots=("/workspace",)),
                SemanticGuardrail(
                    judge=FakeJudge("SCORE: 0.9\nREASONING: fine"),
                    task_context="test",
                ),
            ]
        )
        await chain.check("read_file", {"path": "/workspace/x.py"})

    @pytest.mark.asyncio
    async def test_async_guardrail_in_chain_blocks(self) -> None:
        chain = GuardrailChain(
            guardrails=[
                PathGuardrail(allowed_roots=("/workspace",)),
                SemanticGuardrail(
                    judge=FakeJudge("SCORE: 0.1\nREASONING: bad"),
                    task_context="test",
                    threshold=0.7,
                ),
            ]
        )
        with pytest.raises(LLMRecoverableError):
            await chain.check("write_file", {"path": "/workspace/x.py"})

    @pytest.mark.asyncio
    async def test_sync_guardrail_blocks_before_async_runs(self) -> None:
        chain = GuardrailChain(
            guardrails=[
                PathGuardrail(allowed_roots=("/workspace",)),
                SemanticGuardrail(
                    judge=ErrorJudge(),  # would fail if reached
                    task_context="test",
                ),
            ]
        )
        with pytest.raises(UserFixableError):
            await chain.check("read_file", {"path": "/etc/passwd"})
