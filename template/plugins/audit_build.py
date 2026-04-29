"""``tasks audit:build`` — parse the project and persist the audit graph."""

from __future__ import annotations

import sys

from pyarnes_tasks.plugin_base import ModulePlugin


class AuditBuild(ModulePlugin):
    """``uv run tasks audit:build`` — parse roots and persist audit graph.json."""

    name = "audit:build"
    description = "Parse configured roots and persist .pyarnes/audit/graph.json"

    def call(self, argv: list[str]) -> int:
        """Run the audit:build task in-process via a sys.argv shim."""
        from pyarnes_tasks.audit_build import main  # noqa: PLC0415

        original = sys.argv
        sys.argv = ["audit:build", *argv]
        try:
            return main()
        finally:
            sys.argv = original
