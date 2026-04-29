"""Render the code-review graph via graphify."""

from __future__ import annotations

from pyarnes_tasks.plugin_base import ShellPlugin


class GraphRender(ShellPlugin):
    """``uv run tasks graph:render`` — graphify the current project."""

    name = "graph:render"
    description = "graphify the current project"
    cmd = ("graphify", ".")
    requires_bin = ("graphify",)
