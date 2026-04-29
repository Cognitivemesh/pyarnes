"""Markdown lint via pymarkdown."""

from __future__ import annotations

from pyarnes_tasks.plugin_base import ShellPlugin


class MdLint(ShellPlugin):
    """``uv run tasks md-lint`` — pymarkdown scan over the project."""

    name = "md-lint"
    description = "pymarkdown scan over the project"
    cmd = ("uv", "run", "pymarkdown", "scan")
    targets = (".",)
