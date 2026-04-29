"""Shared helpers for the ``codeburn:*`` plugins.

This module is loaded as a sibling file by the codeburn plugins (which
prepend the plugins directory to ``sys.path`` inside their ``call()``).
The leading underscore tells the plugin loader to skip this file
(see ``plugin_loader.py``).
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
    dedupe,
    parse_session_calls,
)
from pyarnes_core.observability import log_warning
from pyarnes_core.observe.logger import configure_logging, get_logger
from pyarnes_harness.capture.tool_log import ToolCallEntry

__all__ = [
    "DiscoveredSession",
    "configure_codeburn_logging",
    "filter_by_project",
    "filter_excludes",
    "load_sessions",
    "render_table",
    "short_name",
]


def render_table(rows, totals) -> None:  # type: ignore[no-untyped-def]
    """Render a small column-aligned table to stdout. Used by burn/codeburn plugins."""
    headers = list(totals.keys())
    all_rows = [*rows, totals]
    widths = [max(len(h), *(len(str(r[h])) for r in all_rows)) for h in headers]
    sep = "  "
    fmt = sep.join(f"{{:<{w}}}" for w in widths)
    divider = sep.join("-" * w for w in widths)
    print(fmt.format(*headers))  # noqa: T201
    print(divider)  # noqa: T201
    for row in rows:
        print(fmt.format(*[str(row[h]) for h in headers]))  # noqa: T201
    print(divider)  # noqa: T201
    print(fmt.format(*[str(totals[h]) for h in headers]))  # noqa: T201


_WORKSPACE_DIRS = frozenset(
    {
        "GitHub",
        "GitLab",
        "Bitbucket",
        "repos",
        "projects",
        "code",
        "dev",
        "workspace",
        "src",
        "work",
    }
)


def short_name(project: str) -> str:
    """Decode an encoded project directory name to a human-readable slug.

    Claude Code encodes ``/Users/x/GitHub/my-app`` as ``-Users-x-GitHub-my-app``.
    We find the last known workspace directory and take everything after it,
    preserving hyphens that are part of the project name.
    Falls back to the last dash-segment for non-standard layouts.
    """
    parts = project.lstrip("-").split("-")
    for i in range(len(parts) - 1, 0, -1):
        if parts[i] in _WORKSPACE_DIRS:
            remainder = parts[i + 1 :]
            if remainder:
                return "-".join(remainder)
    return parts[-1] if parts else project


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
    return [s for s in sessions if not any(fnmatch.fnmatchcase(s.project, pat) for pat in patterns)]
