"""Run pytest with coverage reporting."""

from __future__ import annotations

from pyarnes_tasks.plugin_base import ShellPlugin


class TestCov(ShellPlugin):
    """``uv run tasks test:cov`` — pytest with coverage and term-missing report."""

    name = "test:cov"
    description = "pytest with coverage and term-missing report"
    cmd = ("uv", "run", "pytest", "--cov", "--cov-report=term-missing")
    targets = ("tests",)
    accepts_no_tests = True
