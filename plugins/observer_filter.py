"""Filter JSONL observability events."""

from __future__ import annotations

import sys

from pyarnes_tasks.plugin_base import ModulePlugin


class ObserverFilter(ModulePlugin):
    """``uv run tasks observer:filter`` — filter JSONL events."""

    name = "observer:filter"
    description = "Filter JSONL observability events"

    def call(self, argv: list[str]) -> int:
        """Run the observer:filter task in-process via a sys.argv shim."""
        from pyarnes_tasks.observer_filter import main  # noqa: PLC0415

        original = sys.argv
        sys.argv = ["observer:filter", *argv]
        try:
            return main()
        finally:
            sys.argv = original
