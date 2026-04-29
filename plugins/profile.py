"""Profile via pyinstrument."""

from __future__ import annotations

from pyarnes_tasks.plugin_base import ShellPlugin


class Profile(ShellPlugin):
    """``uv run tasks profile`` — pyinstrument profiler."""

    name = "profile"
    description = "pyinstrument profiler"
    cmd = ("uv", "run", "pyinstrument")
