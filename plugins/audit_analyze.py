"""``tasks audit:analyze`` — god nodes, surprising connections, suggested questions."""

from __future__ import annotations

import sys

from pyarnes_tasks.plugin_base import ModulePlugin


class AuditAnalyze(ModulePlugin):
    """``uv run tasks audit:analyze`` — graph analysis with god nodes and questions."""

    name = "audit:analyze"
    description = "God nodes, surprising connections, suggested questions"

    def call(self, argv: list[str]) -> int:
        """Run the audit:analyze task in-process via a sys.argv shim."""
        from pyarnes_tasks.audit_analyze import main  # noqa: PLC0415

        original = sys.argv
        sys.argv = ["audit:analyze", *argv]
        try:
            return main()
        finally:
            sys.argv = original
