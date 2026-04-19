"""Tests for the pyarnes-tasks CLI — argument forwarding and task dispatch."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from pyarnes_tasks.cli import _run_task


class _FakeResult:
    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode


class TestRunTaskExtraArgs:
    """`_run_task` should append ``extra`` to the resolved command before exec."""

    def test_no_extra_args_runs_bare_command(self, tmp_path) -> None:
        tasks = {"echo": ["echo", "hello"]}
        with patch("subprocess.run", return_value=_FakeResult()) as mock_run:
            code = _run_task("echo", tasks, tmp_path)
        assert code == 0
        assert mock_run.call_args.args[0] == ["echo", "hello"]

    def test_extra_args_are_appended_to_task_command(self, tmp_path) -> None:
        tasks = {"graph:blast": ["code-review-graph", "blast"]}
        extra = ["packages/core/src/file.py", "--json"]
        with patch("subprocess.run", return_value=_FakeResult()) as mock_run:
            code = _run_task("graph:blast", tasks, tmp_path, extra)
        assert code == 0
        assert mock_run.call_args.args[0] == [
            "code-review-graph",
            "blast",
            "packages/core/src/file.py",
            "--json",
        ]

    def test_unknown_task_returns_nonzero_without_running(self, tmp_path) -> None:
        tasks: dict[str, list[str]] = {}
        with patch("subprocess.run") as mock_run:
            code = _run_task("nope", tasks, tmp_path)
        assert code == 1
        mock_run.assert_not_called()


class TestMainDoubleDashSeparator:
    """``--`` splits task names from forwarded args; only the last task gets them."""

    def test_single_task_with_forwarded_args(self) -> None:
        tasks = {"graph:blast": ["code-review-graph", "blast"]}
        argv = ["tasks", "graph:blast", "--", "path/to/file.py"]
        with (
            patch("sys.argv", argv),
            patch("pyarnes_tasks.cli._build_tasks", return_value=(tasks, "/tmp")),
            patch("subprocess.run", return_value=_FakeResult()) as mock_run,
            pytest.raises(SystemExit) as exc,
        ):
            from pyarnes_tasks.cli import main
            main()
        assert exc.value.code == 0
        assert mock_run.call_args.args[0] == ["code-review-graph", "blast", "path/to/file.py"]

    def test_multiple_tasks_only_last_receives_extra(self) -> None:
        tasks = {
            "first": ["echo", "first"],
            "second": ["echo", "second"],
        }
        argv = ["tasks", "first", "second", "--", "extra"]
        calls: list[list[str]] = []
        with (
            patch("sys.argv", argv),
            patch("pyarnes_tasks.cli._build_tasks", return_value=(tasks, "/tmp")),
            patch(
                "subprocess.run",
                side_effect=lambda cmd, **_kw: calls.append(cmd) or _FakeResult(),
            ),
            pytest.raises(SystemExit),
        ):
            from pyarnes_tasks.cli import main
            main()
        assert calls == [
            ["echo", "first"],            # no extra
            ["echo", "second", "extra"],  # extra appended to last task only
        ]
