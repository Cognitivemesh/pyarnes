"""Watch mode for the pytest suite."""

from __future__ import annotations

from pyarnes_tasks.plugin_base import ShellPlugin


class TestWatch(ShellPlugin):
    """``uv run tasks test:watch`` — pytest_watch over tests."""

    name = "test:watch"
    description = "pytest_watch over tests"
    cmd = ("uv", "run", "pytest_watch")
    targets = ("tests",)


class Watch(ShellPlugin):
    """``uv run tasks watch`` — alias for test:watch."""

    name = "watch"
    description = "alias for test:watch"
    cmd = ("uv", "run", "pytest_watch")
    targets = ("tests",)
