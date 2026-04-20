"""Atom: clock — ISO timestamps and monotonic durations.

Separated from ``ToolCallLogger`` so any call site (audit log, loop
retry-timer, capture layer) uses the same primitive. Consumers should
call ``start_timer`` once *outside* any retry loop so
``monotonic_duration`` reflects the full wall-clock span.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

__all__ = [
    "iso_now",
    "monotonic_duration",
    "start_timer",
]


def iso_now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(tz=UTC).isoformat()


def start_timer() -> tuple[str, float]:
    """Capture an ISO timestamp and a monotonic reference point.

    Returns:
        ``(started_at_iso, start_monotonic)``. Pass the monotonic value
        to :func:`monotonic_duration` later to get wall-clock duration.
    """
    return iso_now(), time.monotonic()


def monotonic_duration(start_mono: float) -> tuple[str, float]:
    """Compute ``(finished_at_iso, duration_seconds)`` from *start_mono*.

    Args:
        start_mono: The monotonic value returned by :func:`start_timer`.

    Returns:
        ``(finished_at_iso, duration_seconds)``.
    """
    return iso_now(), time.monotonic() - start_mono
