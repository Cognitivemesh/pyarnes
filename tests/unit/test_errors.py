"""Tests for the four-error taxonomy."""

from __future__ import annotations

import pytest

from pyarnes_core.errors import (
    HarnessError,
    LLMRecoverableError,
    Severity,
    TransientError,
    UnexpectedError,
    UserFixableError,
)


class TestTransientError:
    """TransientError should carry retry metadata."""

    def test_defaults(self) -> None:
        err = TransientError(message="timeout")
        assert str(err) == "timeout"
        assert err.max_retries == 2
        assert err.retry_delay_seconds == 1.0
        assert err.severity == Severity.MEDIUM

    def test_custom_retries(self) -> None:
        err = TransientError(message="rate limit", max_retries=5, retry_delay_seconds=2.0)
        assert err.max_retries == 5
        assert err.retry_delay_seconds == 2.0

    def test_is_harness_error(self) -> None:
        assert issubclass(TransientError, HarnessError)


class TestLLMRecoverableError:
    """LLMRecoverableError carries optional tool_call_id."""

    def test_defaults(self) -> None:
        err = LLMRecoverableError(message="bad JSON")
        assert err.tool_call_id is None

    def test_with_tool_call_id(self) -> None:
        err = LLMRecoverableError(message="schema mismatch", tool_call_id="call_123")
        assert err.tool_call_id == "call_123"


class TestUserFixableError:
    """UserFixableError should include a human-readable hint."""

    def test_prompt_hint(self) -> None:
        err = UserFixableError(message="auth needed", prompt_hint="Enter API key")
        assert err.prompt_hint == "Enter API key"

    def test_default_hint(self) -> None:
        err = UserFixableError(message="missing config")
        assert err.prompt_hint == ""


class TestUnexpectedError:
    """UnexpectedError wraps the original exception."""

    def test_wraps_original(self) -> None:
        original = RuntimeError("boom")
        err = UnexpectedError(message="internal", original=original)
        assert err.original is original
        assert err.severity == Severity.CRITICAL

    def test_default_none(self) -> None:
        err = UnexpectedError(message="unknown")
        assert err.original is None


class TestHarnessErrorHierarchy:
    """All error types inherit from HarnessError and Exception."""

    @pytest.mark.parametrize(
        "cls",
        [TransientError, LLMRecoverableError, UserFixableError, UnexpectedError],
    )
    def test_is_exception(self, cls: type) -> None:
        assert issubclass(cls, Exception)
        assert issubclass(cls, HarnessError)

    def test_context_dict(self) -> None:
        err = HarnessError(message="test", context={"key": "val"})
        assert err.context == {"key": "val"}
