"""Tests for the pyarnes-tasks CLI — argument forwarding and task dispatch."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from pyarnes_tasks.cli import _run_task, main


class TestRunTaskExtraArgs:
    """`_run_task` should append ``extra`` to the resolved command before exec."""

    def test_no_extra_args_runs_bare_command(self, tmp_path) -> None:
        tasks = {"echo": ["echo", "hello"]}
        with patch("subprocess.run", return_value=Mock(returncode=0)) as mock_run:
            code = _run_task("echo", tasks, tmp_path)
        assert code == 0
        assert mock_run.call_args.args[0] == ["echo", "hello"]

    def test_extra_args_are_appended_to_task_command(self, tmp_path) -> None:
        tasks = {"graph:blast": ["code-review-graph", "blast"]}
        extra = ("packages/core/src/file.py", "--json")
        with patch("subprocess.run", return_value=Mock(returncode=0)) as mock_run:
            code = _run_task("graph:blast", tasks, tmp_path, extra)
        assert code == 0
        assert mock_run.call_args.args[0] == [
            "code-review-graph",
            "blast",
            "packages/core/src/file.py",
            "--json",
        ]

    def test_unknown_task_returns_nonzero_without_running(self, tmp_path) -> None:
        with patch("subprocess.run") as mock_run:
            code = _run_task("nope", {}, tmp_path)
        assert code == 1
        mock_run.assert_not_called()


class TestMainDoubleDashSeparator:
    """``--`` splits task names from forwarded args; only the last task gets them."""

    def test_single_task_with_forwarded_args(self) -> None:
        tasks = {"graph:blast": ["code-review-graph", "blast"]}
        with (
            patch("sys.argv", ["tasks", "graph:blast", "--", "path/to/file.py"]),
            patch("pyarnes_tasks.cli._build_tasks", return_value=(tasks, "/tmp")),
            patch("subprocess.run", return_value=Mock(returncode=0)) as mock_run,
            pytest.raises(SystemExit) as exc,
        ):
            main()
        assert exc.value.code == 0
        assert mock_run.call_args.args[0] == ["code-review-graph", "blast", "path/to/file.py"]

    def test_multiple_tasks_only_last_receives_extra(self) -> None:
        tasks = {"first": ["echo", "first"], "second": ["echo", "second"]}
        calls: list[list[str]] = []
        with (
            patch("sys.argv", ["tasks", "first", "second", "--", "extra"]),
            patch("pyarnes_tasks.cli._build_tasks", return_value=(tasks, "/tmp")),
            patch(
                "subprocess.run",
                side_effect=lambda cmd, **_kw: calls.append(cmd) or Mock(returncode=0),
            ),
            pytest.raises(SystemExit),
        ):
            main()
        assert calls == [
            ["echo", "first"],
            ["echo", "second", "extra"],
        ]
