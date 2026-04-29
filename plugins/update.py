"""Update the scaffolded project from its copier template."""

from __future__ import annotations

from pyarnes_tasks.plugin_base import ShellPlugin


class Update(ShellPlugin):
    """``uv run tasks update`` — copier update against the source template."""

    name = "update"
    description = "copier update against the source template"
    cmd = ("uvx", "copier", "update")
