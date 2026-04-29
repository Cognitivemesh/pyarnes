"""Auto-format via ruff format."""

from __future__ import annotations

from pyarnes_tasks.plugin_base import ShellPlugin


class Format(ShellPlugin):
    """``uv run tasks format`` — ruff format."""

    name = "format"
    description = "ruff format across sources and tests"
    cmd = ("uv", "run", "ruff", "format")
    targets = ("sources", "tests")


class FormatCheck(ShellPlugin):
    """``uv run tasks format:check`` — ruff format --check."""

    name = "format:check"
    description = "ruff format --check (CI-safe; no writes)"
    cmd = ("uv", "run", "ruff", "format", "--check")
    targets = ("sources", "tests")
