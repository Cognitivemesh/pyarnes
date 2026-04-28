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

import json
import sys
from pathlib import Path
from typing import Any


def _matches(record: dict[str, Any], *, event_pat: str, session_id: str, level: str) -> bool:
    if event_pat and event_pat.lower() not in record.get("event", "").lower():
        return False
    if session_id and record.get("session_id") != session_id:
        return False
    return not (level and record.get("level", "").lower() != level.lower())


def _filter_lines(lines: Any, *, event_pat: str, session_id: str, level: str) -> int:
    for raw_line in lines:
        raw = raw_line.rstrip("\n")
        if not raw.strip():
            continue
        try:
            record: dict[str, Any] = json.loads(raw)
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


def main() -> int:
    """Entry point — returns a process exit code."""
    args = sys.argv[1:]
    if not args or args[0] in {"-h", "--help"}:
        print(  # noqa: T201
            "usage: tasks observer:filter -- [--event <pat>] [--session <id>] [--level <lvl>] <jsonl_path|->",
            file=sys.stderr,
        )
        return 1

    event_pat, session_id, level, source = _parse_args(args)

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


if __name__ == "__main__":
    sys.exit(main())
