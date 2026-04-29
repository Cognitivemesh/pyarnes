"""``tasks observer:filter -- [options] <jsonl_path|->``: filter JSONL events.

Reads a JSONL log and prints only lines that match the given criteria.
Accepts a file path or ``-`` to read from stdin.

Options::

    --event <pattern>   Keep lines whose ``event`` field contains <pattern>
                        (case-insensitive substring match).
    --session <id>      Keep lines whose ``session_id`` field equals <id>
                        (exact match).
    --level <name>      Keep lines whose ``level`` matches <name>
                        (case-insensitive, e.g. ``warning``).

Multiple options are ANDed.  When no options are given all lines pass through.
Stdlib-only; no third-party dependency.
"""

from __future__ import annotations

import sys

from pyarnes_tasks.plugin_base import ModulePlugin


def _matches(record, *, event_pat: str, session_id: str, level: str) -> bool:  # type: ignore[no-untyped-def]
    if event_pat and event_pat.lower() not in record.get("event", "").lower():
        return False
    if session_id and record.get("session_id") != session_id:
        return False
    return not (level and record.get("level", "").lower() != level.lower())


def _filter_lines(lines, *, event_pat: str, session_id: str, level: str) -> int:  # type: ignore[no-untyped-def]
    import json  # noqa: PLC0415

    for raw_line in lines:
        raw = raw_line.rstrip("\n")
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if _matches(record, event_pat=event_pat, session_id=session_id, level=level):
            print(raw)  # noqa: T201
    return 0


def _parse_args(args: list[str]) -> tuple[str, str, str, str]:
    """Return ``(event_pat, session_id, level, source)``."""
    event_pat = ""
    session_id = ""
    level = ""
    source = "-"

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--event" and i + 1 < len(args):
            i += 1
            event_pat = args[i]
        elif arg == "--session" and i + 1 < len(args):
            i += 1
            session_id = args[i]
        elif arg == "--level" and i + 1 < len(args):
            i += 1
            level = args[i]
        elif not arg.startswith("-"):
            source = arg
        i += 1

    return event_pat, session_id, level, source


class ObserverFilter(ModulePlugin):
    """``uv run tasks observer:filter`` — filter JSONL events."""

    name = "observer:filter"
    description = "Filter JSONL observability events"

    def call(self, argv: list[str]) -> int:
        """Run the observer:filter task in-process."""
        from pathlib import Path  # noqa: PLC0415

        if not argv or argv[0] in {"-h", "--help"}:
            print(  # noqa: T201
                "usage: tasks observer:filter -- [--event <pat>] [--session <id>] [--level <lvl>] <jsonl_path|->",
                file=sys.stderr,
            )
            return 1

        event_pat, session_id, level, source = _parse_args(argv)

        if source == "-":
            try:
                return _filter_lines(sys.stdin, event_pat=event_pat, session_id=session_id, level=level)
            except KeyboardInterrupt:
                return 0

        path = Path(source)
        if not path.is_file():
            print(f"not a file: {path}", file=sys.stderr)  # noqa: T201
            return 1

        with path.open(encoding="utf-8", errors="replace") as fh:
            return _filter_lines(fh, event_pat=event_pat, session_id=session_id, level=level)
