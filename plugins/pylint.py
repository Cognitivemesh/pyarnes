"""Lint via pylint."""

from __future__ import annotations

from pyarnes_tasks.plugin_base import ShellPlugin


class Pylint(ShellPlugin):
    """``uv run tasks pylint`` — pylint over sources."""

    name = "pylint"
    description = "pylint over sources"
    cmd = ("uv", "run", "pylint")
    targets = ("sources",)
