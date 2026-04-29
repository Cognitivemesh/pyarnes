"""Run the pytest suite."""

from __future__ import annotations

from pyarnes_tasks.plugin_base import ShellPlugin


class Test(ShellPlugin):
    """``uv run tasks test`` — pytest over tests."""

    name = "test"
    description = "pytest over tests"
    cmd = ("uv", "run", "pytest")
    targets = ("tests",)
    accepts_no_tests = True
