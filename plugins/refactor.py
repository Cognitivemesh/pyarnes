"""AST-based renames via Bowler (PEP 723 — own deps).

Usage:
    uv run tasks refactor -- --rename OLD_NAME NEW_NAME [PATH ...]

Demonstrates the SCRIPT plugin path with a heavy dep (Bowler) that
nobody wants in the project's main venv. PEP 723 isolates the dep.
"""

# /// script
# requires-python = ">=3.13"
# dependencies = ["bowler>=0.9"]
# ///

from __future__ import annotations

import sys


def _run_refactor(argv: list[str]) -> int:
    """Apply a Bowler rename across the given paths."""
    if len(argv) < 3 or argv[0] != "--rename":  # noqa: PLR2004
        print("usage: refactor --rename OLD NEW [PATH ...]", file=sys.stderr)  # noqa: T201
        return 2
    from bowler import Query  # noqa: PLC0415 — heavy lazy import

    old, new = argv[1], argv[2]
    paths = argv[3:] or ["."]
    Query(paths).select_function(old).rename(new).execute(write=True, silent=False)
    return 0


try:
    from pyarnes_tasks.plugin_base import ScriptPlugin

    class Refactor(ScriptPlugin):
        """``uv run tasks refactor`` — Bowler-driven safe rewrites."""

        name = "refactor"
        description = "AST refactor via Bowler (PEP 723: brings own deps)"

        def run_script(self, argv: list[str]) -> int:
            """Forward to ``_run_refactor``."""
            return _run_refactor(argv)
except ImportError:
    pass


if __name__ == "__main__":
    raise SystemExit(_run_refactor(sys.argv[1:]))
