"""Token cost report across AI coding sessions."""

from __future__ import annotations

import sys

from pyarnes_tasks.plugin_base import ModulePlugin


class BurnReport(ModulePlugin):
    """``uv run tasks burn:report`` — token cost report across AI coding sessions."""

    name = "burn:report"
    description = "Token cost report across AI coding sessions"

    def call(self, argv: list[str]) -> int:
        """Run the burn:report task in-process via a sys.argv shim."""
        from pyarnes_tasks.burn_report import main  # noqa: PLC0415

        original = sys.argv
        sys.argv = ["burn:report", *argv]
        try:
            return main()
        finally:
            sys.argv = original
