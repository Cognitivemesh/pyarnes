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
        tasks = {"audit:check": ["python", "-m", "pyarnes_tasks.audit_check"]}
        extra = ("--root", "packages/core/src")
        with patch("subprocess.run", return_value=Mock(returncode=0)) as mock_run:
            code = _run_task("audit:check", tasks, tmp_path, extra)
        assert code == 0
        assert mock_run.call_args.args[0] == [
            "python",
            "-m",
            "pyarnes_tasks.audit_check",
            "--root",
            "packages/core/src",
        ]

    def test_unknown_task_returns_nonzero_without_running(self, tmp_path) -> None:
        with patch("subprocess.run") as mock_run:
            code = _run_task("nope", {}, tmp_path)
        assert code == 1
        mock_run.assert_not_called()


class TestAuditTasksRegistered:
    """The four ``audit:*`` entries must be wired into the CLI."""

    def test_audit_tasks_present_in_dict(self) -> None:
        from pyarnes_tasks.cli import _build_tasks  # imported lazily so the test stays cheap

        tasks, _root = _build_tasks()
        for name in ("audit:build", "audit:show", "audit:analyze", "audit:check"):
            assert name in tasks, f"missing {name}"
            cmd = tasks[name]
            # All four invoke a `pyarnes_tasks.audit_*` Python module.
            assert any(part.startswith("pyarnes_tasks.audit_") for part in cmd), cmd


class TestMainDoubleDashSeparator:
    """``--`` splits task names from forwarded args; only the last task gets them."""

    def test_single_task_with_forwarded_args(self) -> None:
        tasks = {"audit:check": ["python", "-m", "pyarnes_tasks.audit_check"]}
        with (
            patch("sys.argv", ["tasks", "audit:check", "--", "--root", "src"]),
            patch("pyarnes_tasks.cli._build_tasks", return_value=(tasks, "/tmp")),  # noqa: S108
            patch("subprocess.run", return_value=Mock(returncode=0)) as mock_run,
            pytest.raises(SystemExit) as exc,
        ):
            main()
        assert exc.value.code == 0
        assert mock_run.call_args.args[0] == [
            "python",
            "-m",
            "pyarnes_tasks.audit_check",
            "--root",
            "src",
        ]

    def test_multiple_tasks_only_last_receives_extra(self) -> None:
        tasks = {"first": ["echo", "first"], "second": ["echo", "second"]}
        calls: list[list[str]] = []
        with (
            patch("sys.argv", ["tasks", "first", "second", "--", "extra"]),
            patch("pyarnes_tasks.cli._build_tasks", return_value=(tasks, "/tmp")),  # noqa: S108
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
