"""Waste-detection scan with A-F health grade and 48 h trend.

Detectors are pure functions: ``(sessions, claude_dir) -> [Finding]``.
Each finding carries a severity (``pyarnes_core.errors.Severity``) and
an estimate of token / cost savings so the grade can be computed
deterministically and the CLI can rank findings without re-scoring.

Read-only invariant: this module never writes to ``~/.claude``. The
only on-disk side effect is the 48 h snapshot under
``~/.cache/pyarnes/codeburn/``, written via
:func:`pyarnes_core.atomic_write.write_private`.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from pyarnes_core.observability import estimate_tokens

from pyarnes_bench.burn.normalize import normalize_tool
from pyarnes_bench.burn.types import Cost
from pyarnes_core.atomic_write import write_private
from pyarnes_core.errors import Severity
from pyarnes_core.observability import dumps, iso_now, to_jsonable
from pyarnes_harness.capture.tool_log import ToolCallEntry

__all__ = [
    "Finding",
    "HealthGrade",
    "OptimizeReport",
    "SessionInput",
    "all_detectors",
    "compute_grade",
    "detect_bloated_claude_md",
    "detect_cache_creation_overhead",
    "detect_ghost_agents_skills",
    "detect_low_read_edit_ratio",
    "detect_rereads",
    "detect_uncapped_bash",
    "detect_unused_mcp",
    "load_previous_report",
    "save_report",
    "snapshot_dir",
]


class HealthGrade(Enum):
    """A-F health grade, weighted by severity-adjusted finding count."""

    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"


@dataclass(frozen=True, slots=True)
class Finding:
    """One waste pattern flagged by a detector."""

    code: str
    severity: Severity
    title: str
    detail: str
    est_tokens_saved: int = 0
    est_cost_saved: Cost | None = None
    fix: str = ""
    evidence: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict."""
        return {
            "code": self.code,
            "severity": self.severity.value,
            "title": self.title,
            "detail": self.detail,
            "est_tokens_saved": self.est_tokens_saved,
            "est_cost_saved": self.est_cost_saved.as_dict() if self.est_cost_saved else None,
            "fix": self.fix,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class SessionInput:
    """One session's worth of data fed into the detectors."""

    session_id: str
    project: str
    entries: Sequence[ToolCallEntry]


@dataclass(frozen=True, slots=True)
class OptimizeReport:
    """Output of :func:`run` — full scan plus 48 h trend."""

    findings: list[Finding]
    grade: HealthGrade
    previous_grade: HealthGrade | None
    delta_48h: dict[str, int]
    generated_at: str

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict."""
        return {
            "findings": [f.as_dict() for f in self.findings],
            "grade": self.grade.value,
            "previous_grade": self.previous_grade.value if self.previous_grade else None,
            "delta_48h": dict(self.delta_48h),
            "generated_at": self.generated_at,
        }


# ── detectors ──────────────────────────────────────────────────────────────


_REREAD_THRESHOLD = 3
_UNCAPPED_BASH_BYTES = 16_384
_LOW_READ_EDIT_RATIO = 0.5
_BLOATED_CLAUDE_MD_BYTES = 16_384
_BLOATED_CLAUDE_MD_IMPORTS = 5
_CACHE_CHURN_MIN_CALLS = 20  # sessions shorter than this are exempt from churn flag
_MCP_TOOL_PARTS = 2  # mcp__<server>__<op> minimum components to extract server name


def detect_rereads(sessions: Sequence[SessionInput], claude_dir: Path | None = None) -> list[Finding]:  # noqa: ARG001
    """Flag files Read more than :data:`_REREAD_THRESHOLD` times."""
    counts: Counter[str] = Counter()
    for s in sessions:
        for e in s.entries:
            if normalize_tool(e.tool) != "Read":
                continue
            path = e.arguments.get("file_path") if isinstance(e.arguments, dict) else None
            if isinstance(path, str):
                counts[path] += 1
    findings: list[Finding] = []
    for path, n in counts.most_common():
        if n < _REREAD_THRESHOLD:
            break
        findings.append(
            Finding(
                code="REREAD_FILES",
                severity=Severity.MEDIUM,
                title=f"{path} read {n} times",
                detail="Repeated reads of the same file across sessions waste cache budget.",
                est_tokens_saved=(n - 1) * 1500,
                fix=f"Add an `@{path}` import to CLAUDE.md so the file is loaded once at session start.",
                evidence=[f"{n} Read calls"],
            )
        )
    return findings


def detect_low_read_edit_ratio(
    sessions: Sequence[SessionInput],
    claude_dir: Path | None = None,  # noqa: ARG001
) -> list[Finding]:
    """Flag sessions where edits run far ahead of reads (blind edits)."""
    findings: list[Finding] = []
    for s in sessions:
        reads = sum(1 for e in s.entries if normalize_tool(e.tool) == "Read")
        edits = sum(1 for e in s.entries if normalize_tool(e.tool) in {"Edit", "Write"})
        if edits == 0:
            continue
        ratio = reads / edits
        if ratio < _LOW_READ_EDIT_RATIO:
            findings.append(
                Finding(
                    code="LOW_READ_EDIT_RATIO",
                    severity=Severity.HIGH,
                    title=f"Session {s.session_id}: {reads} reads / {edits} edits (ratio {ratio:.2f})",
                    detail="Editing without reading first is a leading cause of regressions.",
                    fix="Require a Read before each Edit in the agent prompt.",
                    evidence=[s.session_id],
                )
            )
    return findings


def detect_uncapped_bash(
    sessions: Sequence[SessionInput],
    claude_dir: Path | None = None,  # noqa: ARG001
) -> list[Finding]:
    """Flag Bash results that exceed :data:`_UNCAPPED_BASH_BYTES`."""
    findings: list[Finding] = []
    for s in sessions:
        for e in s.entries:
            if normalize_tool(e.tool) != "Bash":
                continue
            result = e.result
            if not isinstance(result, str):
                continue
            if len(result.encode("utf-8")) <= _UNCAPPED_BASH_BYTES:
                continue
            cmd = e.arguments.get("command") if isinstance(e.arguments, dict) else ""
            if not isinstance(cmd, str):
                cmd = ""
            findings.append(
                Finding(
                    code="UNCAPPED_BASH",
                    severity=Severity.MEDIUM,
                    title=f"Bash output {len(result):,} bytes (no head/tail)",
                    detail="Large Bash outputs blow up context; cap with `| head -n 200` or pipe through `wc`.",
                    est_tokens_saved=estimate_tokens(result),
                    fix=f"Run `{cmd} | head -n 200` (or similar) instead.",
                    evidence=[s.session_id],
                )
            )
    return findings


def _declared_mcp_servers(claude_dir: Path) -> set[str]:
    settings = claude_dir / "settings.json"
    if not settings.is_file():
        return set()
    try:
        config = json.loads(settings.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(config, dict):
        return set()
    block = config.get("mcpServers")
    if not isinstance(block, dict):
        return set()
    return {str(k) for k in block}


def _used_mcp_servers(sessions: Sequence[SessionInput]) -> set[str]:
    used: set[str] = set()
    for s in sessions:
        for e in s.entries:
            if not e.tool.startswith("mcp__"):
                continue
            parts = e.tool.split("__", maxsplit=2)
            if len(parts) >= _MCP_TOOL_PARTS:
                used.add(parts[1])
    return used


def detect_unused_mcp(
    sessions: Sequence[SessionInput],
    claude_dir: Path | None = None,
) -> list[Finding]:
    """Flag MCP tools declared in settings but never invoked."""
    target = claude_dir if claude_dir is not None else Path.home() / ".claude"
    declared = _declared_mcp_servers(target)
    if not declared:
        return []
    unused = sorted(declared - _used_mcp_servers(sessions))
    if not unused:
        return []
    settings = target / "settings.json"
    return [
        Finding(
            code="UNUSED_MCP",
            severity=Severity.LOW,
            title=f"{len(unused)} MCP server(s) configured but never called",
            detail="Each MCP server adds tools to every session prompt; remove unused ones.",
            est_tokens_saved=len(unused) * 800,
            fix=f"Remove these from {settings}: {', '.join(unused)}",
            evidence=unused,
        )
    ]


def detect_ghost_agents_skills(
    sessions: Sequence[SessionInput],
    claude_dir: Path | None = None,
) -> list[Finding]:
    """Flag agents/skills declared on disk but never invoked."""
    if claude_dir is None:
        claude_dir = Path.home() / ".claude"
    findings: list[Finding] = []
    for kind, suffix in (("agent", "agents"), ("skill", "skills")):
        directory = claude_dir / suffix
        if not directory.is_dir():
            continue
        declared = sorted({p.stem for p in directory.glob("*.md")})
        if not declared:
            continue
        invoked = _invoked_subagents(sessions) if kind == "agent" else _invoked_skills(sessions)
        ghosts = sorted(set(declared) - invoked)
        if ghosts:
            findings.append(
                Finding(
                    code=f"GHOST_{kind.upper()}S",
                    severity=Severity.LOW,
                    title=f"{len(ghosts)} {kind}(s) declared but never invoked",
                    detail=f"Each {kind} ships its prompt into every session; prune the unused ones.",
                    est_tokens_saved=len(ghosts) * 500,
                    fix=f"Remove or merge: {', '.join(ghosts)}",
                    evidence=ghosts,
                )
            )
    return findings


def _invoked_subagents(sessions: Sequence[SessionInput]) -> set[str]:
    invoked: set[str] = set()
    for s in sessions:
        for e in s.entries:
            if normalize_tool(e.tool) != "Task":
                continue
            sub = e.arguments.get("subagent_type") if isinstance(e.arguments, dict) else None
            if isinstance(sub, str):
                invoked.add(sub)
    return invoked


def _invoked_skills(sessions: Sequence[SessionInput]) -> set[str]:
    invoked: set[str] = set()
    for s in sessions:
        for e in s.entries:
            if e.tool.lower() != "skill":
                continue
            name = e.arguments.get("skill") if isinstance(e.arguments, dict) else None
            if isinstance(name, str):
                invoked.add(name)
    return invoked


def detect_bloated_claude_md(
    sessions: Sequence[SessionInput],  # noqa: ARG001
    claude_dir: Path | None = None,
) -> list[Finding]:
    """Flag oversize CLAUDE.md or excessive ``@-imports``."""
    if claude_dir is None:
        claude_dir = Path.home() / ".claude"
    candidates = [claude_dir / "CLAUDE.md", Path.cwd() / "CLAUDE.md"]
    findings: list[Finding] = []
    for path in candidates:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        size = len(text.encode("utf-8"))
        imports = sum(1 for line in text.splitlines() if line.lstrip().startswith("@"))
        if size > _BLOATED_CLAUDE_MD_BYTES or imports > _BLOATED_CLAUDE_MD_IMPORTS:
            findings.append(
                Finding(
                    code="BLOATED_CLAUDE_MD",
                    severity=Severity.MEDIUM,
                    title=f"{path}: {size:,} bytes, {imports} @-imports",
                    detail="CLAUDE.md is loaded into every prompt; trim it to keep context cheap.",
                    est_tokens_saved=size // 4,
                    fix="Move project-specific content into per-package READMEs and link by path.",
                    evidence=[str(path)],
                )
            )
    return findings


def detect_cache_creation_overhead(
    sessions: Sequence[SessionInput],
    claude_dir: Path | None = None,  # noqa: ARG001
) -> list[Finding]:
    """Flag sessions whose cache-creation cost dwarfs cache reads.

    Per-call cache numbers are not in :class:`ToolCallEntry`; this is a
    placeholder detector that fires only when the call stream looks
    unusually edit-heavy and cache-light (more than 20 calls with no
    Read at all). Real cache analysis lives in ``burn:report`` totals.
    """
    findings: list[Finding] = []
    for s in sessions:
        if len(s.entries) < _CACHE_CHURN_MIN_CALLS:
            continue
        reads = sum(1 for e in s.entries if normalize_tool(e.tool) == "Read")
        if reads == 0:
            findings.append(
                Finding(
                    code="CACHE_CHURN",
                    severity=Severity.LOW,
                    title=f"Session {s.session_id}: {len(s.entries)} calls, no Reads",
                    detail="Sessions without Read calls cache poorly; expect repeated cache writes.",
                    fix="Read at least one project file early so prompt-cache hits compound.",
                    evidence=[s.session_id],
                )
            )
    return findings


def all_detectors() -> list[Any]:
    """Return every detector function in the canonical order."""
    return [
        detect_rereads,
        detect_low_read_edit_ratio,
        detect_uncapped_bash,
        detect_unused_mcp,
        detect_ghost_agents_skills,
        detect_bloated_claude_md,
        detect_cache_creation_overhead,
    ]


# ── grade ──────────────────────────────────────────────────────────────────


_GRADE_THRESHOLDS: list[tuple[int, HealthGrade]] = [
    (0, HealthGrade.A),
    (3, HealthGrade.B),
    (9, HealthGrade.C),
    (19, HealthGrade.D),
]


def compute_grade(findings: Sequence[Finding]) -> HealthGrade:
    """Map a finding list to an A-F :class:`HealthGrade`.

    Score = sum of ``Severity.weight`` over findings. Thresholds
    (inclusive upper bound):

    * 0       -> A
    * 1-3     -> B
    * 4-9     -> C
    * 10-19   -> D
    * 20+     -> F
    """
    score = sum(f.severity.weight for f in findings)
    for ceiling, grade in _GRADE_THRESHOLDS:
        if score <= ceiling:
            return grade
    return HealthGrade.F


# ── 48h trend ──────────────────────────────────────────────────────────────


_SNAPSHOT_RETENTION_HOURS = 96  # twice the trend window so the diff still has data


def snapshot_dir(home: Path | None = None) -> Path:
    """Return the directory used for 48 h snapshots."""
    base = home if home is not None else Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    return base / "pyarnes" / "codeburn"


def save_report(report: OptimizeReport, home: Path | None = None) -> Path:
    """Write *report* atomically under :func:`snapshot_dir` and return the path.

    Also prunes snapshots older than :data:`_SNAPSHOT_RETENTION_HOURS`
    so the cache directory stays bounded across many invocations.
    """
    target_dir = snapshot_dir(home)
    target_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    iso_date = report.generated_at.replace(":", "-")
    path = target_dir / f"optimize-{iso_date}.json"
    write_private(path, dumps(to_jsonable(report.as_dict())) + "\n")
    _prune_snapshots(target_dir)
    return path


def _prune_snapshots(target_dir: Path) -> None:
    cutoff = (datetime.now(tz=UTC) - timedelta(hours=_SNAPSHOT_RETENTION_HOURS)).timestamp()
    for old in target_dir.glob("optimize-*.json"):
        try:
            if old.stat().st_mtime < cutoff:
                old.unlink()
        except OSError:
            continue


def load_previous_report(*, home: Path | None = None, max_age_hours: int = 48) -> OptimizeReport | None:
    """Return the most recent snapshot ≤ *max_age_hours* old, or ``None``.

    Args:
        home: Override for the snapshot root (used in tests).
        max_age_hours: Hours of look-back. The default 48 mirrors
            CodeBurn's "what changed since yesterday" framing.
    """
    target_dir = snapshot_dir(home)
    if not target_dir.is_dir():
        return None
    candidates = sorted(target_dir.glob("optimize-*.json"), reverse=True)
    cutoff = datetime.now(tz=UTC) - timedelta(hours=max_age_hours)
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        ts = data.get("generated_at")
        if not isinstance(ts, str):
            continue
        try:
            when = datetime.fromisoformat(ts)
        except ValueError:
            continue
        if when < cutoff:
            continue
        return _rehydrate_report(data)
    return None


def _rehydrate_report(data: dict[str, Any]) -> OptimizeReport:
    findings = [
        Finding(
            code=item["code"],
            severity=Severity(item["severity"]),
            title=item["title"],
            detail=item["detail"],
            est_tokens_saved=int(item.get("est_tokens_saved", 0)),
            est_cost_saved=_cost_from_dict(item.get("est_cost_saved")),
            fix=item.get("fix", ""),
            evidence=list(item.get("evidence", [])),
        )
        for item in data.get("findings", [])
    ]
    return OptimizeReport(
        findings=findings,
        grade=HealthGrade(data["grade"]),
        previous_grade=HealthGrade(data["previous_grade"]) if data.get("previous_grade") else None,
        delta_48h=dict(data.get("delta_48h", {})),
        generated_at=data["generated_at"],
    )


def _cost_from_dict(payload: Any) -> Cost | None:
    if not isinstance(payload, dict):
        return None
    amount = payload.get("amount")
    currency = payload.get("currency")
    if not isinstance(amount, str) or not isinstance(currency, str):
        return None
    return Cost(amount=Decimal(amount), currency=currency)


# ── orchestration ──────────────────────────────────────────────────────────


def run(
    sessions: Sequence[SessionInput],
    *,
    claude_dir: Path | None = None,
    home: Path | None = None,
) -> OptimizeReport:
    """Run all detectors, compute the grade, and load the 48 h trend.

    Caller is responsible for persisting the report via
    :func:`save_report` if a snapshot is desired.
    """
    findings: list[Finding] = []
    for detector in all_detectors():
        findings.extend(detector(sessions, claude_dir))
    findings.sort(key=lambda f: f.severity.weight, reverse=True)

    grade = compute_grade(findings)
    previous = load_previous_report(home=home)
    delta = _delta(findings, previous)
    return OptimizeReport(
        findings=findings,
        grade=grade,
        previous_grade=previous.grade if previous else None,
        delta_48h=delta,
        generated_at=iso_now(),
    )


def _delta(current: Sequence[Finding], previous: OptimizeReport | None) -> dict[str, int]:
    """Return the count delta keyed by severity name."""
    cur_counts: Counter[str] = Counter(f.severity.value for f in current)
    if previous is None:
        return {}
    prev_counts: Counter[str] = Counter(f.severity.value for f in previous.findings)
    keys = set(cur_counts) | set(prev_counts)
    return {k: cur_counts.get(k, 0) - prev_counts.get(k, 0) for k in sorted(keys)}
