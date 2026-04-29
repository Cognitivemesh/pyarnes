"""``tasks audit:check`` — detect dead code, cycles, complexity, boundary violations.

Non-zero exit on HIGH findings — suitable for CI gates.
"""

from __future__ import annotations

import sys

from pyarnes_tasks.plugin_base import ModulePlugin


class AuditCheck(ModulePlugin):
    """``uv run tasks audit:check`` — detect findings and exit non-zero on HIGH."""

    name = "audit:check"
    description = "Detect unused / circular / duplicate / hot / boundary issues; non-zero on HIGH"

    def call(self, argv: list[str]) -> int:
        """Run the audit:check task in-process via a sys.argv shim."""
        from pyarnes_tasks.audit_check import main  # noqa: PLC0415

        original = sys.argv
        sys.argv = ["audit:check", *argv]
        try:
            return main()
        finally:
            sys.argv = original
