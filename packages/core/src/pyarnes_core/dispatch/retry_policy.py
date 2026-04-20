"""Atom: retry policy — merge loop config with per-error overrides.

``TransientError.max_retries`` and ``TransientError.retry_delay_seconds``
must be honored alongside ``LoopConfig`` values. This atom produces
the effective policy by taking the maximum of config and per-exception
hints.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "RetryPolicy",
    "merge_retry_caps",
    "next_delay",
]


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Effective retry policy after merging config + per-error overrides.

    Attributes:
        max_retries: Cap on retry attempts (not including the initial try).
        base_delay_seconds: Seed for exponential backoff.
    """

    max_retries: int
    base_delay_seconds: float


def merge_retry_caps(
    config_max: int,
    config_delay: float,
    *,
    error_max: int | None = None,
    error_delay: float | None = None,
) -> RetryPolicy:
    """Merge loop config with a transient error's override hints.

    The merge takes the ``max`` of both sources — a tool that asks for
    more retries than the loop default should get them; a loop
    configured with a higher floor should not be lowered by a tool.

    Args:
        config_max: ``LoopConfig.max_retries``.
        config_delay: ``LoopConfig.retry_base_delay``.
        error_max: Override from the raised ``TransientError`` (if any).
        error_delay: Override from the raised ``TransientError`` (if any).

    Returns:
        The effective :class:`RetryPolicy` for the current attempt.
    """
    effective_max = config_max if error_max is None else max(config_max, error_max)
    effective_delay = (
        config_delay if error_delay is None else max(config_delay, error_delay)
    )
    return RetryPolicy(
        max_retries=effective_max,
        base_delay_seconds=effective_delay,
    )


def next_delay(policy: RetryPolicy, attempt: int) -> float:
    """Return the delay before the next retry with exponential backoff.

    Args:
        policy: Effective policy for this call.
        attempt: Zero-based attempt index (0 for the first retry).

    Returns:
        ``base_delay_seconds * 2**attempt``.
    """
    return policy.base_delay_seconds * (2**attempt)
