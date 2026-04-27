"""Per-call KPIs derived from a session's ``ToolCallEntry`` stream.

Returns plain dataclasses; rendering is the CLI's responsibility.
Every KPI is *additive* across sessions so a project-level summary is
just a sum-and-rebalance over per-session KPIs.

KPI definitions
---------------

* **one_shot_rate** — Fraction of file edits (``Edit``/``Write``) that
  are not followed within ``window`` calls by another edit on the
  same path or a failing test command (``Bash`` with ``is_error``).
* **retry_loops** — Count of ``failing-Bash → fix-Edit → Bash`` triples.
* **cache_hit_rate** — ``cache_read_tokens / (cache_read_tokens +
  cache_creation_tokens + input_tokens)``. ``0.0`` when no tokens are
  recorded (avoids ``ZeroDivisionError`` and matches "no caching" intent).
* **read_edit_ratio** — ``Read calls / Edit calls`` (∞ as ``-1`` for
  serialisation when there are no edits at all).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from pyarnes_bench.burn.classify import classify_window
from pyarnes_bench.burn.normalize import normalize_tool
from pyarnes_bench.burn.types import Cost, TokenUsage
from pyarnes_harness.capture.tool_log import ToolCallEntry

__all__ = [
    "ProjectKpis",
    "SessionKpis",
    "compute_project_kpis",
    "compute_session_kpis",
]


_DEFAULT_WINDOW = 6


@dataclass(frozen=True, slots=True)
class SessionKpis:
    """KPI bundle for a single session."""

    session_id: str
    project: str
    total_calls: int
    unique_tools: int
    one_shot_rate: float
    retry_loops: int
    cache_hit_rate: float
    read_edit_ratio: float
    cost_total: Decimal
    currency: str
    cost_by_bucket: dict[str, str]  # TaskKind.value -> "0.1234"
    cost_by_tool: dict[str, str]    # canonical tool -> "0.1234"

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict (suitable for JSON output)."""
        return {
            "session_id": self.session_id,
            "project": self.project,
            "total_calls": self.total_calls,
            "unique_tools": self.unique_tools,
            "one_shot_rate": self.one_shot_rate,
            "retry_loops": self.retry_loops,
            "cache_hit_rate": self.cache_hit_rate,
            "read_edit_ratio": self.read_edit_ratio,
            "cost_total": str(self.cost_total),
            "currency": self.currency,
            "cost_by_bucket": dict(self.cost_by_bucket),
            "cost_by_tool": dict(self.cost_by_tool),
        }


@dataclass(frozen=True, slots=True)
class ProjectKpis:
    """Project-wide KPI aggregate over many sessions."""

    project: str
    sessions: int
    total_calls: int
    avg_one_shot_rate: float
    total_retry_loops: int
    avg_cache_hit_rate: float
    cost_total: Decimal
    currency: str
    cost_by_bucket: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict."""
        return {
            "project": self.project,
            "sessions": self.sessions,
            "total_calls": self.total_calls,
            "avg_one_shot_rate": self.avg_one_shot_rate,
            "total_retry_loops": self.total_retry_loops,
            "avg_cache_hit_rate": self.avg_cache_hit_rate,
            "cost_total": str(self.cost_total),
            "currency": self.currency,
            "cost_by_bucket": dict(self.cost_by_bucket),
        }


def compute_session_kpis(
    entries: Sequence[ToolCallEntry],
    *,
    session_id: str,
    project: str,
    cost: Cost | None = None,
    window: int = _DEFAULT_WINDOW,
) -> SessionKpis:
    """Return a :class:`SessionKpis` for a session's call stream.

    Args:
        entries: Tool calls in chronological order.
        session_id: Identifier carried into the KPI record.
        project: Project slug carried into the KPI record.
        cost: Total session cost (already summed). When ``None`` the
            ``cost_*`` fields default to ``Decimal(0)`` / empty maps.
        window: Look-ahead used by the one-shot rate definition.
    """
    canonical = [normalize_tool(e.tool) for e in entries]
    buckets = classify_window(entries)

    one_shot = _one_shot_rate(entries, canonical, window=window)
    retries = _retry_loops(entries, canonical)
    cache_rate = _cache_hit_rate(entries)
    re_ratio = _read_edit_ratio(canonical)

    total_amount = cost.amount if cost is not None else Decimal(0)
    currency = cost.currency if cost is not None else ""
    cost_by_bucket = _split_cost(buckets, total_amount, key=lambda k: k.value)
    cost_by_tool = _split_cost(canonical, total_amount, key=lambda k: k)

    return SessionKpis(
        session_id=session_id,
        project=project,
        total_calls=len(entries),
        unique_tools=len(set(canonical)),
        one_shot_rate=one_shot,
        retry_loops=retries,
        cache_hit_rate=cache_rate,
        read_edit_ratio=re_ratio,
        cost_total=total_amount,
        currency=currency,
        cost_by_bucket={k: f"{v:.6f}" for k, v in cost_by_bucket.items()},
        cost_by_tool={k: f"{v:.6f}" for k, v in cost_by_tool.items()},
    )


def compute_project_kpis(sessions: Sequence[SessionKpis]) -> ProjectKpis:
    """Aggregate per-session KPIs into a single project-level record."""
    if not sessions:
        return ProjectKpis(
            project="",
            sessions=0,
            total_calls=0,
            avg_one_shot_rate=0.0,
            total_retry_loops=0,
            avg_cache_hit_rate=0.0,
            cost_total=Decimal(0),
            currency="",
        )
    project = sessions[0].project
    n = len(sessions)
    total_cost = sum((s.cost_total for s in sessions), Decimal(0))
    bucket_totals: dict[str, Decimal] = {}
    for s in sessions:
        for k, v in s.cost_by_bucket.items():
            bucket_totals[k] = bucket_totals.get(k, Decimal(0)) + Decimal(v)
    return ProjectKpis(
        project=project,
        sessions=n,
        total_calls=sum(s.total_calls for s in sessions),
        avg_one_shot_rate=sum(s.one_shot_rate for s in sessions) / n,
        total_retry_loops=sum(s.retry_loops for s in sessions),
        avg_cache_hit_rate=sum(s.cache_hit_rate for s in sessions) / n,
        cost_total=total_cost,
        currency=sessions[0].currency,
        cost_by_bucket={k: f"{v:.6f}" for k, v in bucket_totals.items()},
    )


# ── helpers ────────────────────────────────────────────────────────────────


def _one_shot_rate(
    entries: Sequence[ToolCallEntry],
    canonical: Sequence[str],
    *,
    window: int,
) -> float:
    edits = [(i, e) for i, e in enumerate(entries) if canonical[i] in {"Edit", "Write"}]
    if not edits:
        return 0.0
    one_shots = sum(
        1
        for i, edit in edits
        if _is_one_shot(edit, entries[i + 1 : i + 1 + window], canonical[i + 1 : i + 1 + window])
    )
    return one_shots / len(edits)


def _is_one_shot(
    edit: ToolCallEntry,
    follow_entries: Sequence[ToolCallEntry],
    follow_canonical: Sequence[str],
) -> bool:
    target = edit.arguments.get("file_path") if isinstance(edit.arguments, dict) else None
    for j, tool in enumerate(follow_canonical):
        if tool in {"Edit", "Write"}:
            other = (
                follow_entries[j].arguments.get("file_path")
                if isinstance(follow_entries[j].arguments, dict)
                else None
            )
            if other == target:
                return False
        if tool == "Bash" and follow_entries[j].is_error:
            return False
    return True


def _retry_loops(entries: Sequence[ToolCallEntry], canonical: Sequence[str]) -> int:
    n = len(entries)
    loops = 0
    for i in range(n - 2):
        first, last = entries[i], entries[i + 2]
        if (
            canonical[i] == "Bash"
            and first.is_error
            and canonical[i + 1] == "Edit"
            and canonical[i + 2] == "Bash"
            and not last.is_error
        ):
            loops += 1
    return loops


def _cache_hit_rate(entries: Sequence[ToolCallEntry]) -> float:
    usage = _aggregate_usage(entries)
    denom = usage.input_tokens + usage.cache_creation_tokens + usage.cache_read_tokens
    if denom == 0:
        return 0.0
    return usage.cache_read_tokens / denom


def _read_edit_ratio(canonical: Sequence[str]) -> float:
    reads = sum(1 for t in canonical if t == "Read")
    edits = sum(1 for t in canonical if t in {"Edit", "Write"})
    if edits == 0:
        return -1.0 if reads > 0 else 0.0
    return reads / edits


def _aggregate_usage(entries: Sequence[ToolCallEntry]) -> TokenUsage:
    """Collapse per-call token counts into one :class:`TokenUsage`.

    ``ToolCallEntry`` only carries ``token_in`` / ``token_out``; cache
    counts come from the assistant turn that produced the call but the
    upstream parser does not propagate them per-call. We treat them as
    ``0`` here — the rest of the pipeline uses ``SessionBurn`` for cache
    accounting.
    """
    inp = sum(e.token_in or 0 for e in entries)
    out = sum(e.token_out or 0 for e in entries)
    return TokenUsage(input_tokens=inp, output_tokens=out)


def _split_cost(
    keys: Sequence[Any],
    total: Decimal,
    *,
    key: Any,
) -> dict[str, Decimal]:
    """Split *total* cost proportionally across the labels in *keys*.

    No call-level cost data exists, so we attribute cost by call count
    — every call in a session shares the session's per-call average.
    Sums to *total* up to the rounding chosen at format time.
    """
    if not keys or total == 0:
        return {}
    counts: dict[str, int] = {}
    for k in keys:
        label = key(k)
        counts[label] = counts.get(label, 0) + 1
    n = sum(counts.values())
    return {label: total * Decimal(c) / Decimal(n) for label, c in counts.items()}
