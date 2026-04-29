"""Static lint via ruff."""

from __future__ import annotations

from pyarnes_tasks.plugin_base import ShellPlugin


class Lint(ShellPlugin):
    """``uv run tasks lint`` — ruff check across sources and tests."""

    name = "lint"
    description = "ruff check across sources and tests"
    cmd = ("uv", "run", "ruff", "check")
    targets = ("sources", "tests")


class LintFix(ShellPlugin):
    """``uv run tasks lint:fix`` — ruff check --fix."""

    name = "lint:fix"
    description = "ruff check --fix across sources and tests"
    cmd = ("uv", "run", "ruff", "check", "--fix")
    targets = ("sources", "tests")
