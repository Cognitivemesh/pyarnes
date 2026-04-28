"""Priority-ordered error classifier mapping exceptions to recovery actions.

Classifies exceptions raised during tool execution into a ``ClassifiedError``
struct that tells the loop how to respond: retry, compress context, rotate
credentials, fall back to another model, or surface to the model.

Rules are evaluated in priority order (first match wins):
  1. Rate-limit (HTTP 429, ``TransientError``) → retryable
  2. Context-length → should_compress
  3. Auth (HTTP 401/403, auth keywords) → should_rotate_credential
  4. Provider/server error (HTTP 5xx) → should_fallback
  5. LLMRecoverableError → not retryable, surface to model
  6. Generic → no recovery action
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from pyarnes_core.errors import LLMRecoverableError, TransientError

_HTTP_RATE_LIMIT = 429
_HTTP_PAYLOAD_TOO_LARGE = 413
_HTTP_UNAUTHORIZED = 401
_HTTP_FORBIDDEN = 403
_HTTP_SERVER_ERROR_MIN = 500
_HTTP_SERVER_ERROR_MAX = 600

__all__ = [
    "ClassifiedError",
    "classify_error",
]

_CONTEXT_PATTERNS = re.compile(
    r"context.length|maximum.token|token.limit|context.window|too.many.tokens",
    re.IGNORECASE,
)
_AUTH_PATTERNS = re.compile(
    r"invalid.api.key|authentication.failed|unauthorized|permission.denied",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ClassifiedError:
    """Recovery prescription produced by :func:`classify_error`.

    Attributes:
        retryable: The call may succeed if retried (rate-limit, transient).
        should_compress: Context window is too large; compact before retrying.
        should_rotate_credential: API key is invalid or expired.
        should_fallback: Try an alternate model or provider.
    """

    retryable: bool = False
    should_compress: bool = False
    should_rotate_credential: bool = False
    should_fallback: bool = False


def _status_code(exc: Exception) -> int | None:
    """Extract HTTP status code from provider-style exceptions."""
    return getattr(exc, "status_code", None) or getattr(exc, "http_status", None)


# Priority-ordered rule list: (predicate, ClassifiedError)
def _build_rules() -> list[tuple[Callable[[Exception], bool], ClassifiedError]]:
    def _is_rate_limit(exc: Exception) -> bool:
        code = _status_code(exc)
        return isinstance(exc, TransientError) or code == _HTTP_RATE_LIMIT

    def _is_context_length(exc: Exception) -> bool:
        code = _status_code(exc)
        if code == _HTTP_PAYLOAD_TOO_LARGE:
            return True
        return bool(_CONTEXT_PATTERNS.search(str(exc)))

    def _is_auth(exc: Exception) -> bool:
        code = _status_code(exc)
        if code in (_HTTP_UNAUTHORIZED, _HTTP_FORBIDDEN):
            return True
        return bool(_AUTH_PATTERNS.search(str(exc)))

    def _is_server_error(exc: Exception) -> bool:
        code = _status_code(exc)
        return code is not None and _HTTP_SERVER_ERROR_MIN <= code < _HTTP_SERVER_ERROR_MAX

    def _is_llm_recoverable(exc: Exception) -> bool:
        return isinstance(exc, LLMRecoverableError)

    return [
        (_is_rate_limit, ClassifiedError(retryable=True)),
        (_is_context_length, ClassifiedError(should_compress=True)),
        (_is_auth, ClassifiedError(should_rotate_credential=True)),
        (_is_server_error, ClassifiedError(should_fallback=True)),
        (_is_llm_recoverable, ClassifiedError()),
    ]


_RULES = _build_rules()
_DEFAULT = ClassifiedError()


def classify_error(exc: Exception) -> ClassifiedError:
    """Return a ``ClassifiedError`` for the given exception.

    Evaluates rules in priority order; returns the first match.
    Falls back to a fully-negative ``ClassifiedError`` for unknowns.

    Args:
        exc: The exception to classify.

    Returns:
        Appropriate ``ClassifiedError`` recovery prescription.
    """
    for predicate, classification in _RULES:
        if predicate(exc):
            return classification
    return _DEFAULT
