"""Typed audit-event emitters.

These mirror the shape of the cross-cutting emitters in
``pyarnes_core.observability.events`` (lifecycle / tool / guardrail) — same
mandatory ``session_id`` / ``trace_id`` / ``step`` keyword-only context — but
are bench-feature-specific so they live next to the audit code rather than in
the slim core observability module. Phase-2 work that adds report rendering or
an MCP server can extend this file without touching core.
"""

from __future__ import annotations

from typing import Any, Literal

from pyarnes_core.observability import log_event
from pyarnes_core.observability.ports import LoggerPort

__all__ = [
    "AuditAnalysisKind",
    "AuditFindingCategory",
    "AuditFindingSeverity",
    "log_audit_analyzed",
    "log_audit_finding",
    "log_audit_indexed",
]


# Kept narrow on purpose: callers should not invent free-form kinds. Adding a
# new kind here is the same surface change as adding a new column to the
# observability schema, so the type alias makes that contract explicit.
AuditAnalysisKind = Literal["god_nodes", "surprises", "questions"]
AuditFindingCategory = Literal[
    "unused_file",
    "unused_export",
    "unused_dep",
    "circular_import",
    "duplicate_block",
    "complexity_hotspot",
    "boundary_violation",
    "feature_flag",
]
AuditFindingSeverity = Literal["high", "medium", "low"]


def log_audit_indexed(  # noqa: PLR0913
    logger: LoggerPort,
    root: str,
    *,
    files: int,
    nodes: int,
    edges: int,
    duration_ms: float,
    session_id: str,
    trace_id: str,
    step: int,
) -> None:
    """Emit an ``audit.indexed`` event after a graph build completes.

    Args:
        logger: A logger satisfying :class:`LoggerPort`.
        root: Root path that was indexed (typically ``str(Path.cwd())``).
        files: Number of ``.py`` files parsed.
        nodes: Total nodes added to the graph.
        edges: Total edges added to the graph.
        duration_ms: Wall-clock time the build took, in milliseconds.
        session_id: Session identifier (keyword-only, required).
        trace_id: Trace identifier for distributed tracing (keyword-only, required).
        step: Current step number in the execution (keyword-only, required).
    """
    log_event(
        logger,
        "audit.indexed",
        root=root,
        files=files,
        nodes=nodes,
        edges=edges,
        duration_ms=duration_ms,
        session_id=session_id,
        trace_id=trace_id,
        step=step,
    )


def log_audit_analyzed(
    logger: LoggerPort,
    kind: AuditAnalysisKind,
    *,
    count: int,
    session_id: str,
    trace_id: str,
    step: int,
) -> None:
    """Emit an ``audit.analyzed`` event after a structural analysis completes.

    Args:
        logger: A logger satisfying :class:`LoggerPort`.
        kind: One of ``god_nodes``, ``surprises``, ``questions``.
        count: How many entries the analysis produced.
        session_id: Session identifier (keyword-only, required).
        trace_id: Trace identifier for distributed tracing (keyword-only, required).
        step: Current step number in the execution (keyword-only, required).
    """
    log_event(
        logger,
        "audit.analyzed",
        kind=kind,
        count=count,
        session_id=session_id,
        trace_id=trace_id,
        step=step,
    )


def log_audit_finding(  # noqa: PLR0913
    logger: LoggerPort,
    category: AuditFindingCategory,
    target: str,
    severity: AuditFindingSeverity,
    *,
    session_id: str,
    trace_id: str,
    step: int,
    detail: dict[str, Any] | None = None,
) -> None:
    """Emit an ``audit.finding`` event for a single detector hit.

    Args:
        logger: A logger satisfying :class:`LoggerPort`.
        category: Detector that produced the finding.
        target: Node id, file path, or symbol the finding is about.
        severity: ``high``, ``medium``, or ``low``.
        session_id: Session identifier (keyword-only, required).
        trace_id: Trace identifier for distributed tracing (keyword-only, required).
        step: Current step number in the execution (keyword-only, required).
        detail: Optional extra fields specific to the detector (e.g. cycle path,
            duplicate hash, complexity rank). Kept JSON-serialisable so the
            event survives a round trip through stderr.
    """
    log_event(
        logger,
        "audit.finding",
        category=category,
        target=target,
        severity=severity,
        detail=detail or {},
        session_id=session_id,
        trace_id=trace_id,
        step=step,
    )
