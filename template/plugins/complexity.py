"""Complexity composite — radon:cc, radon:mi."""

from __future__ import annotations

from pyarnes_tasks.plugin_base import CompositePlugin


class Complexity(CompositePlugin):
    """``uv run tasks complexity`` — cyclomatic complexity + maintainability index."""

    name = "complexity"
    description = "radon:cc -> radon:mi"
    subtasks = ("radon:cc", "radon:mi")
