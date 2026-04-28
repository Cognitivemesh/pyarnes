"""Four canonical error types for agentic harness loops.

Error taxonomy
--------------
1. **TransientError** — retry with exponential backoff (network blips, rate limits).
2. **LLMRecoverableError** — return the error as a ``ToolMessage`` so the model
   can adjust its next action. Keeps the agent loop running.
3. **UserFixableError** — interrupt execution and surface to a human for input.
4. **UnexpectedError** — bubble up immediately for debugging / post-mortem.

Inspired by Anthropic's tool-handler pattern (errors become tool results) and
Stripe's production harness (retry cap at two attempts).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__all__ = [
    "HarnessError",
    "LLMRecoverableError",
    "Severity",
    "TransientError",
    "UnexpectedError",
    "UserFixableError",
]


class Severity(Enum):
    """Error severity levels.

    Used to classify the impact of a harness error so that callers can
    decide how aggressively to react (e.g. log-only vs. page on-call).
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def weight(self) -> int:
        """Return a comparable integer weight (higher = more severe).

        Lets callers rank, sort, or threshold-filter by severity without
        re-declaring the order. The numbers are evaluation weights, not
        ordinals — gaps reflect that one ``HIGH`` should outweigh two
        ``MEDIUM``s in the codeburn health-grade scoring.
        """
        return _SEVERITY_WEIGHTS[self]


_SEVERITY_WEIGHTS: dict[Severity, int] = {
    Severity.LOW: 1,
    Severity.MEDIUM: 3,
    Severity.HIGH: 7,
    Severity.CRITICAL: 12,
}


@dataclass(frozen=True, slots=True)
class HarnessError(Exception):
    """Base error for all harness-specific failures.

    Attributes:
        message: Human-readable description of the failure.
        context: Arbitrary key-value metadata attached to the error.
        severity: How critical the failure is.
    """

    message: str
    context: dict[str, Any] = field(default_factory=dict)
    severity: Severity = Severity.MEDIUM

    def __post_init__(self) -> None:
        """Restore ``Exception.args`` that the dataclass ``__init__`` skips."""
        # Without this, ``e.args == ()`` and Sentry / structlog /
        # ``logger.error(*e.args)`` all lose the payload.
        object.__setattr__(self, "args", (self.message,))

    def __str__(self) -> str:  # noqa: D105
        return self.message


# ── 1. Transient — retry with back-off ────────────────────────────────────


@dataclass(frozen=True, slots=True)
class TransientError(HarnessError):
    """Retriable failure (network timeout, rate-limit, etc.).

    Attributes:
        max_retries: Upper bound on retry attempts (Stripe-style cap at 2).
        retry_delay_seconds: Initial delay before the first retry.
    """

    max_retries: int = 2
    retry_delay_seconds: float = 1.0


# ── 2. LLM-recoverable — feed back as ToolMessage ─────────────────────────


@dataclass(frozen=True, slots=True)
class LLMRecoverableError(HarnessError):
    """Error the model can recover from by adjusting its next action.

    The harness converts this into a ``ToolMessage`` with ``is_error=True``
    so the LLM sees the failure as context, not a crash.

    Attributes:
        tool_call_id: ID of the tool call that triggered this error.
    """

    tool_call_id: str | None = None


# ── 3. User-fixable — interrupt for human input ───────────────────────────


@dataclass(frozen=True, slots=True)
class UserFixableError(HarnessError):
    """Requires human intervention before the loop can continue.

    Attributes:
        prompt_hint: Suggested question / instructions to show the user.
    """

    prompt_hint: str = ""


# ── 4. Unexpected — bubble up for debugging ────────────────────────────────


@dataclass(frozen=True, slots=True)
class UnexpectedError(HarnessError):
    """Catch-all for truly unexpected failures.

    Wraps the original exception so callers can inspect the root cause.

    Attributes:
        original: The underlying exception, if available.
    """

    original: BaseException | None = None
    severity: Severity = Severity.CRITICAL
