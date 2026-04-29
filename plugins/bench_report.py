"""Render a markdown table from a JSONL benchmark result file."""

from __future__ import annotations

import sys

from pyarnes_tasks.plugin_base import ModulePlugin


class BenchReport(ModulePlugin):
    """``uv run tasks bench:report`` — render a markdown table from JSONL."""

    name = "bench:report"
    description = "Render a markdown table from a JSONL benchmark result file"

    def call(self, argv: list[str]) -> int:
        """Run the bench:report task in-process via a sys.argv shim."""
        from pyarnes_tasks.bench_report import main  # noqa: PLC0415

        original = sys.argv
        sys.argv = ["bench:report", *argv]
        try:
            return main()
        finally:
            sys.argv = original
