"""Audit findings — the unit each detector emits."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from pyarnes_bench.audit.events import AuditFindingCategory, AuditFindingSeverity

__all__ = ["Finding", "FindingSummary", "summarize"]


@dataclass(frozen=True, slots=True)
class Finding:
    """A single audit finding produced by one of the detectors.

    ``target`` is whatever identifies the offending element — a node id, a
    file path, a dependency name. ``detail`` carries detector-specific extras
    (cycle path, duplicate hash, complexity rank). Both must be JSON-safe so
    the finding can be logged via ``log_audit_finding`` and round-tripped
    through stderr without loss.
    """

    category: AuditFindingCategory
    target: str
    severity: AuditFindingSeverity
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FindingSummary:
    """Counters returned by :func:`summarize`."""

    total: int
    by_category: dict[str, int]
    by_severity: dict[str, int]
    has_high: bool


def summarize(findings: Iterable[Finding]) -> FindingSummary:
    """Aggregate findings by category and severity.

    Used by ``audit:check`` to decide whether the run should exit non-zero
    (any HIGH finding) and to drive the human-readable summary.
    """
    findings = list(findings)
    by_category = Counter(f.category for f in findings)
    by_severity = Counter(f.severity for f in findings)
    return FindingSummary(
        total=len(findings),
        by_category=dict(by_category),  # ty: ignore[no-matching-overload]
        by_severity=dict(by_severity),  # ty: ignore[no-matching-overload]
        has_high=by_severity.get("high", 0) > 0,
    )
