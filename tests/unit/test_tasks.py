"""Smoke tests for the pyarnes-tasks CLI task runner."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent.parent


@pytest.mark.slow
def test_help_task_lists_known_tasks() -> None:
    """uv run tasks help exits 0 and lists core task names."""
    result = subprocess.run(  # noqa: S603, S607
        ["uv", "run", "tasks", "help"],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0
    assert "test" in result.stdout
    assert "lint" in result.stdout
    assert "check" in result.stdout


@pytest.mark.slow
def test_unknown_task_exits_nonzero() -> None:
    """uv run tasks <unknown> exits with a non-zero code."""
    result = subprocess.run(  # noqa: S603, S607
        ["uv", "run", "tasks", "this_task_does_not_exist_xyz"],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        check=False,
    )
    assert result.returncode != 0
