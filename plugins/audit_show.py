"""``tasks audit:show`` — print a human-readable summary of the persisted graph."""

from __future__ import annotations

import sys

from pyarnes_tasks.plugin_base import ModulePlugin


class AuditShow(ModulePlugin):
    """``uv run tasks audit:show`` — print a human-readable graph summary."""

    name = "audit:show"
    description = "Print a human-readable summary of the persisted audit graph"

    def call(self, argv: list[str]) -> int:
        """Run the audit:show task in-process via a sys.argv shim."""
        from pyarnes_tasks.audit_show import main  # noqa: PLC0415

        original = sys.argv
        sys.argv = ["audit:show", *argv]
        try:
            return main()
        finally:
            sys.argv = original
