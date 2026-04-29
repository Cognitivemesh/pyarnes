"""Import and execute an adopter benchmark suite."""

from __future__ import annotations

import sys

from pyarnes_tasks.plugin_base import ModulePlugin


class BenchRun(ModulePlugin):
    """``uv run tasks bench:run`` — import and execute an adopter suite."""

    name = "bench:run"
    description = "Import and execute an adopter benchmark suite"

    def call(self, argv: list[str]) -> int:
        """Run the bench:run task in-process via a sys.argv shim."""
        from pyarnes_tasks.bench_run import main  # noqa: PLC0415

        original = sys.argv
        sys.argv = ["bench:run", *argv]
        try:
            return main()
        finally:
            sys.argv = original
