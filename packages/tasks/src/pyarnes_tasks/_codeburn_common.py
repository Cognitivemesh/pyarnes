"""Shared helpers for the ``codeburn:*`` tasks.

Lives under ``pyarnes_tasks`` so each task module imports it directly
rather than reaching across packages. Domain logic stays in
``pyarnes_bench.burn``; this file only owns CLI plumbing (logging
setup, session discovery, slug filtering).
"""

from __future__ import annotations

import fnmatch
import os
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from pyarnes_bench.burn import (
    ClaudeCodeProvider,
    SessionInput,
    dedupe,
    parse_session_calls,
)
from pyarnes_core.observability import log_warning
from pyarnes_core.observe.logger import configure_logging, get_logger
from pyarnes_harness.capture.tool_log import ToolCallEntry
from pyarnes_tasks.burn_report import short_name

__all__ = [
    "DiscoveredSession",
    "configure_codeburn_logging",
    "filter_by_project",
    "filter_excludes",
    "load_sessions",
    "to_session_inputs",
]


@dataclass(frozen=True, slots=True)
class DiscoveredSession:
    """One session file plus its parsed call stream."""

    session_id: str
    project: str  # short slug, not the encoded directory name
    path: Path
    entries: tuple[ToolCallEntry, ...]


def configure_codeburn_logging() -> None:
    """Configure stderr JSONL logging for a codeburn task.

    Honours ``PYARNES_LOG_LEVEL`` (default ``INFO``) so callers can
    raise verbosity without touching code. Stdout stays untouched —
    rendered tables / JSON go there.
    """
    level = os.environ.get("PYARNES_LOG_LEVEL", "INFO")
    configure_logging(level=level, json=True, stream=sys.stderr)


def _discover_session_files(base: Path | None) -> list[Path]:
    provider = ClaudeCodeProvider()
    effective = base if base is not None else provider.DEFAULT_BASE
    if not effective.is_dir():
        return []
    return sorted(effective.glob(provider.session_glob))


def load_sessions(base: Path | None = None, *, dedup: bool = True) -> list[DiscoveredSession]:
    """Walk the CC project directory and return parsed sessions.

    Args:
        base: Override discovery root. Defaults to the provider default.
        dedup: When True, drop replayed/duplicate calls per session.
    """
    logger = get_logger(__name__)
    out: list[DiscoveredSession] = []
    for path in _discover_session_files(base):
        try:
            entries = parse_session_calls(path)
        except OSError as exc:
            log_warning(logger, "codeburn.session.unreadable", path=str(path), reason=str(exc))
            continue
        if dedup:
            entries = list(dedupe(entries))
        slug = short_name(path.parent.name)
        out.append(
            DiscoveredSession(
                session_id=path.stem,
                project=slug,
                path=path,
                entries=tuple(entries),
            )
        )
    return out


def filter_by_project(sessions: Iterable[DiscoveredSession], project: str | None) -> list[DiscoveredSession]:
    """Return sessions whose project matches *project* (no-op when ``None``)."""
    if not project:
        return list(sessions)
    return [s for s in sessions if s.project == project]


def filter_excludes(
    sessions: Iterable[DiscoveredSession],
    patterns: Sequence[str],
) -> list[DiscoveredSession]:
    """Drop sessions whose project slug matches any glob in *patterns*."""
    if not patterns:
        return list(sessions)
    return [
        s for s in sessions
        if not any(fnmatch.fnmatchcase(s.project, pat) for pat in patterns)
    ]


def to_session_inputs(sessions: Iterable[DiscoveredSession]) -> list[SessionInput]:
    """Adapter: ``DiscoveredSession`` → ``SessionInput`` for the optimize layer."""
    return [
        SessionInput(session_id=s.session_id, project=s.project, entries=list(s.entries))
        for s in sessions
    ]
