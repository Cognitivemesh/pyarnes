"""Type-check via ty."""

from __future__ import annotations

from pyarnes_tasks.plugin_base import ShellPlugin


class Typecheck(ShellPlugin):
    """``uv run tasks typecheck`` — ty check across sources."""

    name = "typecheck"
    description = "Static type-check via ty"
    cmd = ("uv", "run", "ty", "check")
    targets = ("sources",)
