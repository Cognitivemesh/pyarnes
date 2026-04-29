"""Dead-code detection via vulture (PEP 723 — own deps)."""

# /// script
# requires-python = ">=3.13"
# dependencies = ["vulture>=2.10"]
# ///

from __future__ import annotations

import subprocess
import sys


def _run_vulture(argv: list[str]) -> int:
    """Invoke the ``vulture`` CLI in this script's PEP 723 venv."""
    cmd = ["vulture", *argv, "--min-confidence", "80"]
    return subprocess.run(cmd, check=False).returncode  # noqa: S603


try:
    from pyarnes_tasks.plugin_base import ScriptPlugin

    class Vulture(ScriptPlugin):
        """``uv run tasks vulture`` — dead code detection."""

        name = "vulture"
        description = "Dead code detection (PEP 723: brings own vulture)"
        targets = ("sources",)

        def run_script(self, argv: list[str]) -> int:
            """Forward to the standalone ``_run_vulture`` helper."""
            return _run_vulture(argv)
except ImportError:
    pass


if __name__ == "__main__":
    raise SystemExit(_run_vulture(sys.argv[1:]))
