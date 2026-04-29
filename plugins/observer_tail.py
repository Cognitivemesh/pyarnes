"""``tasks observer:tail -- <jsonl_path|->``: stream JSONL events with colour.

Reads a JSONL log produced by pyarnes and pretty-prints each event.
Accepts a file path or ``-`` to read from stdin.

When given a file path the tool prints all existing lines, then follows
new content (like ``tail -f``) until CTRL-C.

Output format per line::

    [timestamp] LEVEL  event_name  key=value key=value …

Stdlib + ANSI escapes only — no third-party dependency.
"""

from __future__ import annotations

import sys

from pyarnes_tasks.plugin_base import ModulePlugin

# ANSI level colours — dim for debug, bold red for critical.
_LEVEL_COLOUR: dict[str, str] = {
    "debug": "\033[2m",  # dim
    "info": "\033[36m",  # cyan
    "warning": "\033[33m",  # yellow
    "error": "\033[31m",  # red
    "critical": "\033[1;31m",  # bold red
}
_RESET = "\033[0m"

_POLL_INTERVAL = 0.2  # seconds between file-size checks when following


def _format_line(raw: str) -> str:
    """Parse one JSONL line and return a coloured human-readable string."""
    import json  # noqa: PLC0415
    from typing import Any  # noqa: PLC0415

    try:
        record: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError:
        return raw  # pass-through if not valid JSON

    ts = record.get("timestamp", "")
    level = record.get("level", "info").lower()
    event = record.get("event", "")

    # Extra fields — skip the structural keys already shown.
    skip = {"timestamp", "level", "event"}
    extras = " ".join(f"{k}={v!r}" for k, v in record.items() if k not in skip)

    colour = _LEVEL_COLOUR.get(level, "")
    level_tag = f"{level.upper():<8}"
    parts = [f"[{ts}]", f"{colour}{level_tag}{_RESET}", event]
    if extras:
        parts.append(f"  {extras}")
    return " ".join(parts)


def _print_line(raw: str) -> None:
    print(_format_line(raw.rstrip("\n")))  # noqa: T201


def _tail_file(path) -> int:  # type: ignore[no-untyped-def]
    """Print all existing lines then follow for new ones until CTRL-C."""
    import time  # noqa: PLC0415

    with path.open(encoding="utf-8", errors="replace") as fh:
        # Drain existing content.
        for line in fh:
            if line.strip():
                _print_line(line)

        # Follow new content.
        try:
            while True:
                line = fh.readline()
                if line:
                    if line.strip():
                        _print_line(line)
                else:
                    time.sleep(_POLL_INTERVAL)
        except KeyboardInterrupt:
            pass
    return 0


def _read_stdin() -> int:
    """Print every JSONL line from stdin until EOF."""
    try:
        for line in sys.stdin:
            if line.strip():
                _print_line(line)
    except KeyboardInterrupt:
        pass
    return 0


class ObserverTail(ModulePlugin):
    """``uv run tasks observer:tail`` — stream JSONL events with colour."""

    name = "observer:tail"
    description = "Tail observability JSONL with colour"

    def call(self, argv: list[str]) -> int:
        """Run the observer:tail task in-process."""
        from pathlib import Path  # noqa: PLC0415

        if not argv or argv[0] in {"-h", "--help"}:
            print("usage: tasks observer:tail -- <jsonl_path|->", file=sys.stderr)  # noqa: T201
            return 1

        source = argv[0]
        if source == "-":
            return _read_stdin()

        path = Path(source)
        if not path.is_file():
            print(f"not a file: {path}", file=sys.stderr)  # noqa: T201
            return 1

        return _tail_file(path)
