"""Maintainability Index via radon (PEP 723 — own deps)."""

# /// script
# requires-python = ">=3.13"
# dependencies = ["radon>=6.0"]
# ///

from __future__ import annotations

import subprocess
import sys


def _run_radon_mi(argv: list[str]) -> int:
    """Invoke the ``radon mi`` CLI in this script's PEP 723 venv."""
    cmd = ["radon", "mi", *argv, "--min", "B"]
    return subprocess.run(cmd, check=False).returncode  # noqa: S603


try:
    from pyarnes_tasks.plugin_base import ScriptPlugin

    class RadonMI(ScriptPlugin):
        """``uv run tasks radon:mi`` — Maintainability Index via radon."""

        name = "radon:mi"
        description = "Maintainability Index (PEP 723: brings own radon)"
        targets = ("sources",)

        def run_script(self, argv: list[str]) -> int:
            """Forward to the standalone ``_run_radon_mi`` helper."""
            return _run_radon_mi(argv)
except ImportError:
    pass


if __name__ == "__main__":
    raise SystemExit(_run_radon_mi(sys.argv[1:]))
