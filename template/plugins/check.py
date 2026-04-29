"""Pre-commit composite — lint, typecheck, test."""

from __future__ import annotations

from pyarnes_tasks.plugin_base import CompositePlugin


class Check(CompositePlugin):
    """``uv run tasks check`` — lint then typecheck then test."""

    name = "check"
    description = "lint -> typecheck -> test (bails on first failure)"
    subtasks = ("lint", "typecheck", "test")
