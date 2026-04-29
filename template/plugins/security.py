"""Security scan via bandit."""

from __future__ import annotations

from pyarnes_tasks.plugin_base import ShellPlugin


class Security(ShellPlugin):
    """``uv run tasks security`` — bandit recursive scan over sources."""

    name = "security"
    description = "bandit security scan over sources"
    cmd = ("uv", "run", "bandit", "-c", "pyproject.toml", "-r")
    targets = ("sources",)
