"""Stream JSONL events with colour."""

from __future__ import annotations

import sys

from pyarnes_tasks.plugin_base import ModulePlugin


class ObserverTail(ModulePlugin):
    """``uv run tasks observer:tail`` — stream JSONL events with colour."""

    name = "observer:tail"
    description = "Tail observability JSONL with colour"

    def call(self, argv: list[str]) -> int:
        """Run the observer:tail task in-process via a sys.argv shim."""
        from pyarnes_tasks.observer_tail import main  # noqa: PLC0415

        original = sys.argv
        sys.argv = ["observer:tail", *argv]
        try:
            return main()
        finally:
            sys.argv = original
