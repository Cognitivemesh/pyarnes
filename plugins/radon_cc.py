"""Cyclomatic complexity via radon (PEP 723 — own deps).

Demonstrates the SCRIPT-plugin pattern: PEP 723 inline metadata declares
the script's deps, so adopters who want this task don't have to add
`radon` to their project's dev group. ``uv run plugins/radon_cc.py`` is
how the dispatcher invokes us — that resolves PEP 723 in an ephemeral
venv. The parent process imports this file only to register the class
in the global plugin registry; that import path uses the project venv,
where ``pyarnes_tasks`` is available.
"""

# /// script
# requires-python = ">=3.13"
# dependencies = ["radon>=6.0"]
# ///

from __future__ import annotations

import subprocess
import sys


def _run_radon_cc(argv: list[str]) -> int:
    """Invoke the ``radon cc`` CLI in this script's PEP 723 venv."""
    cmd = [
        "radon",
        "cc",
        *argv,
        "--min",
        "B",
        "--average",
        "--total-average",
        "--no-assert",
    ]
    return subprocess.run(cmd, check=False).returncode  # noqa: S603


# Registration block: only runs when the parent process imports this
# file via the loader. Under ``uv run plugins/radon_cc.py`` the
# ephemeral venv lacks pyarnes_tasks, so the import fails silently and
# the __main__ block below runs the work directly.
try:
    from pyarnes_tasks.plugin_base import ScriptPlugin

    class RadonCC(ScriptPlugin):
        """``uv run tasks radon:cc`` — cyclomatic complexity via radon."""

        name = "radon:cc"
        description = "Cyclomatic complexity (PEP 723: brings own radon)"
        targets = ("sources",)

        def run_script(self, argv: list[str]) -> int:
            """Forward to the standalone ``_run_radon_cc`` helper."""
            return _run_radon_cc(argv)
except ImportError:
    pass


if __name__ == "__main__":
    raise SystemExit(_run_radon_cc(sys.argv[1:]))
