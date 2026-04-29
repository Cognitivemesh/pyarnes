"""Blast-radius query via code-review-graph."""

from __future__ import annotations

from pyarnes_tasks.plugin_base import ShellPlugin


class GraphBlast(ShellPlugin):
    """``uv run tasks graph:blast`` — code-review-graph blast-radius CLI."""

    name = "graph:blast"
    description = "code-review-graph blast-radius CLI"
    cmd = ("code-review-graph", "blast")
    requires_bin = ("code-review-graph",)
