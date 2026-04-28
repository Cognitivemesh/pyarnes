"""Molecule: events — typed event emitters with mandatory context fields.

Each emitter wraps log_event() with required context fields (session_id,
trace_id, step) as keyword-only arguments. This shape ensures callers
cannot accidentally omit traceability context.
"""

from __future__ import annotations

from pyarnes_core.observability.bound_logger import log_event
from pyarnes_core.observability.ports import LoggerPort

__all__ = [
    "log_guardrail_violation",
    "log_lifecycle_transition",
    "log_tool_call",
]


def log_lifecycle_transition(  # noqa: PLR0913
    logger: LoggerPort,
    from_phase: str,
    to_phase: str,
    *,
    session_id: str,
    trace_id: str,
    step: int,
) -> None:
    """Emit a lifecycle phase transition event.

    Args:
        logger: A logger satisfying :class:`LoggerPort`.
        from_phase: Source phase name.
        to_phase: Destination phase name.
        session_id: Session identifier (keyword-only, required).
        trace_id: Trace identifier for distributed tracing (keyword-only, required).
        step: Current step number in the execution (keyword-only, required).
    """
    log_event(
        logger,
        "lifecycle.transition",
        from_phase=from_phase,
        to_phase=to_phase,
        session_id=session_id,
        trace_id=trace_id,
        step=step,
    )


def log_tool_call(  # noqa: PLR0913
    logger: LoggerPort,
    tool_name: str,
    *,
    session_id: str,
    trace_id: str,
    step: int,
    duration_ms: float,
    is_error: bool,
) -> None:
    """Emit a tool invocation event.

    Args:
        logger: A logger satisfying :class:`LoggerPort`.
        tool_name: Name of the tool that was called.
        session_id: Session identifier (keyword-only, required).
        trace_id: Trace identifier for distributed tracing (keyword-only, required).
        step: Current step number in the execution (keyword-only, required).
        duration_ms: Execution duration in milliseconds.
        is_error: Whether the tool call resulted in an error.
    """
    log_event(
        logger,
        "tool.call",
        tool_name=tool_name,
        session_id=session_id,
        trace_id=trace_id,
        step=step,
        duration_ms=duration_ms,
        is_error=is_error,
    )


def log_guardrail_violation(  # noqa: PLR0913
    logger: LoggerPort,
    guardrail: str,
    tool: str,
    reason: str,
    *,
    session_id: str,
    trace_id: str,
    step: int,
) -> None:
    """Emit a guardrail violation event.

    Args:
        logger: A logger satisfying :class:`LoggerPort`.
        guardrail: Name of the guardrail that was violated.
        tool: Name of the tool that triggered the violation.
        reason: Human-readable explanation of the violation.
        session_id: Session identifier (keyword-only, required).
        trace_id: Trace identifier for distributed tracing (keyword-only, required).
        step: Current step number in the execution (keyword-only, required).
    """
    log_event(
        logger,
        "guardrail.violation",
        guardrail=guardrail,
        tool=tool,
        reason=reason,
        session_id=session_id,
        trace_id=trace_id,
        step=step,
    )
