"""YAML lint via yamllint."""

from __future__ import annotations

from pyarnes_tasks.plugin_base import ShellPlugin


class YamlLint(ShellPlugin):
    """``uv run tasks yaml-lint`` — yamllint over the project."""

    name = "yaml-lint"
    description = "yamllint over the project"
    cmd = ("uv", "run", "yamllint")
    targets = (".",)
