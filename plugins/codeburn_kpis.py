"""Per-session KPIs across CC sessions."""

from __future__ import annotations

import sys

from pyarnes_tasks.plugin_base import ModulePlugin


class CodeburnKpis(ModulePlugin):
    """``uv run tasks codeburn:kpis`` — per-session KPIs across CC sessions."""

    name = "codeburn:kpis"
    description = "Per-session KPIs across CC sessions"

    def call(self, argv: list[str]) -> int:
        """Run the codeburn:kpis task in-process via a sys.argv shim."""
        from pyarnes_tasks.codeburn_kpis import main  # noqa: PLC0415

        original = sys.argv
        sys.argv = ["codeburn:kpis", *argv]
        try:
            return main()
        finally:
            sys.argv = original
