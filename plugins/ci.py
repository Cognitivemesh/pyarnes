"""CI composite — format:check, lint, typecheck, test:cov, security."""

from __future__ import annotations

from pyarnes_tasks.plugin_base import CompositePlugin


class CI(CompositePlugin):
    """``uv run tasks ci`` — full CI gate, bails on first failure."""

    name = "ci"
    description = "format:check -> lint -> typecheck -> test:cov -> security"
    subtasks = ("format:check", "lint", "typecheck", "test:cov", "security")
