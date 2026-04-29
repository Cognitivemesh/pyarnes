"""Waste-detection scan with A-F health grade."""

from __future__ import annotations

import sys

from pyarnes_tasks.plugin_base import ModulePlugin


class CodeburnOptimize(ModulePlugin):
    """``uv run tasks codeburn:optimize`` — waste-detection scan with A-F health grade."""

    name = "codeburn:optimize"
    description = "Waste-detection scan with A-F health grade"

    def call(self, argv: list[str]) -> int:
        """Run the codeburn:optimize task in-process via a sys.argv shim."""
        from pyarnes_tasks.codeburn_optimize import main  # noqa: PLC0415

        original = sys.argv
        sys.argv = ["codeburn:optimize", *argv]
        try:
            return main()
        finally:
            sys.argv = original
