"""Markdown format via mdformat."""

from __future__ import annotations

from pyarnes_tasks.plugin_base import ShellPlugin


class MdFormat(ShellPlugin):
    """``uv run tasks md-format`` — mdformat over the project."""

    name = "md-format"
    description = "mdformat over the project"
    cmd = ("uv", "run", "mdformat")
    targets = (".",)
