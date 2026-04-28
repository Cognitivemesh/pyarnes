"""Tests for the error classifier."""

from __future__ import annotations

import pytest

from pyarnes_core.errors import LLMRecoverableError, TransientError
from pyarnes_harness.classifier import classify_error

# ── Helpers ────────────────────────────────────────────────────────────────


class _FakeHTTPError(Exception):
    """Minimal stand-in for provider HTTP errors."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


class _ContextLengthError(Exception):
    """Simulates a context-too-long API error."""

    def __init__(self) -> None:
        super().__init__("context length exceeded maximum token limit")


class _AuthError(Exception):
    def __init__(self) -> None:
        super().__init__("invalid_api_key: authentication failed")


# ── Classification tests ───────────────────────────────────────────────────


def test_http_429_is_retryable() -> None:
    exc = _FakeHTTPError(429)
    result = classify_error(exc)
    assert result.retryable is True


def test_http_401_should_rotate_credential() -> None:
    exc = _FakeHTTPError(401)
    result = classify_error(exc)
    assert result.should_rotate_credential is True
    assert result.retryable is False


def test_http_403_should_rotate_credential() -> None:
    exc = _FakeHTTPError(403)
    result = classify_error(exc)
    assert result.should_rotate_credential is True


def test_context_length_should_compress() -> None:
    exc = _ContextLengthError()
    result = classify_error(exc)
    assert result.should_compress is True
    assert result.retryable is False


def test_transient_error_is_retryable() -> None:
    exc = TransientError(message="network blip")
    result = classify_error(exc)
    assert result.retryable is True


def test_llm_recoverable_is_not_retryable() -> None:
    exc = LLMRecoverableError(message="bad args")
    result = classify_error(exc)
    assert result.retryable is False


def test_generic_exception_is_not_retryable() -> None:
    exc = ValueError("something broke")
    result = classify_error(exc)
    assert result.retryable is False
    assert result.should_compress is False
    assert result.should_rotate_credential is False
    assert result.should_fallback is False


def test_http_500_should_fallback() -> None:
    exc = _FakeHTTPError(500)
    result = classify_error(exc)
    assert result.should_fallback is True


def test_auth_keyword_in_message_should_rotate() -> None:
    exc = _AuthError()
    result = classify_error(exc)
    assert result.should_rotate_credential is True


def test_classified_error_is_frozen() -> None:
    result = classify_error(ValueError("x"))
    with pytest.raises(AttributeError):
        result.retryable = True  # type: ignore[misc]
