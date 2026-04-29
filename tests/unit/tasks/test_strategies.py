"""Tests for the four execution strategies — Shell, Script, Module, Composite."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from pyarnes_tasks.registry import PluginRegistry
from pyarnes_tasks.strategies import (
    CompositeStrategy,
    ModuleStrategy,
    ScriptStrategy,
    ShellStrategy,
)


def _completed(returncode: int) -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess(args=[], returncode=returncode)


def test_shell_strategy_runs_subprocess(tmp_path: Path) -> None:
    strategy = ShellStrategy(cmd=("echo", "hi"))
    with patch("pyarnes_tasks.strategies.subprocess.run", return_value=_completed(0)) as run:
        code = strategy.execute(args=("--flag",), cwd=tmp_path)
    assert code == 0
    run.assert_called_once_with(["echo", "hi", "--flag"], check=False, cwd=tmp_path)


def test_shell_strategy_propagates_returncode(tmp_path: Path) -> None:
    strategy = ShellStrategy(cmd=("false",))
    with patch("pyarnes_tasks.strategies.subprocess.run", return_value=_completed(7)):
        assert strategy.execute(args=(), cwd=tmp_path) == 7


def test_shell_strategy_missing_binary(tmp_path: Path) -> None:
    strategy = ShellStrategy(cmd=("definitely-not-a-real-binary-xyz",))
    with patch(
        "pyarnes_tasks.strategies.subprocess.run",
        side_effect=FileNotFoundError(2, "not found", "definitely-not-a-real-binary-xyz"),
    ):
        # Returning non-zero (not raising) keeps the CLI uniform with exit codes.
        assert strategy.execute(args=(), cwd=tmp_path) != 0


def test_script_strategy_invokes_uv_run(tmp_path: Path) -> None:
    plugin_file = tmp_path / "demo.py"
    plugin_file.write_text("print('hi')\n")
    strategy = ScriptStrategy(plugin_file=plugin_file)
    with patch("pyarnes_tasks.strategies.subprocess.run", return_value=_completed(0)) as run:
        code = strategy.execute(args=("a", "b"), cwd=tmp_path)
    assert code == 0
    run.assert_called_once_with(["uv", "run", str(plugin_file), "a", "b"], check=False, cwd=tmp_path)


def test_module_strategy_calls_callable(tmp_path: Path) -> None:
    captured: dict = {}

    def fake(argv: list[str]) -> int:
        captured["argv"] = argv
        return 42

    strategy = ModuleStrategy(callable=fake)
    assert strategy.execute(args=("x", "y"), cwd=tmp_path) == 42
    assert captured["argv"] == ["x", "y"]


def test_composite_strategy_runs_all_subtasks(tmp_path: Path) -> None:
    reg = PluginRegistry()
    calls: list[str] = []

    class _FakePlugin:
        def __init__(self, name: str, code: int) -> None:
            self.name = name
            self.code = code

        def run(self, args: tuple[str, ...], cwd: Path) -> int:
            calls.append(self.name)
            return self.code

    reg.register("a", _FakePlugin("a", 0))
    reg.register("b", _FakePlugin("b", 0))
    strategy = CompositeStrategy(subtasks=("a", "b"), registry=reg)
    assert strategy.execute(args=(), cwd=tmp_path) == 0
    assert calls == ["a", "b"]


def test_composite_strategy_bails_on_first_failure(tmp_path: Path) -> None:
    reg = PluginRegistry()
    calls: list[str] = []

    class _FakePlugin:
        def __init__(self, name: str, code: int) -> None:
            self.name = name
            self.code = code

        def run(self, args: tuple[str, ...], cwd: Path) -> int:
            calls.append(self.name)
            return self.code

    reg.register("a", _FakePlugin("a", 3))
    reg.register("b", _FakePlugin("b", 0))
    strategy = CompositeStrategy(subtasks=("a", "b"), registry=reg)
    assert strategy.execute(args=(), cwd=tmp_path) == 3
    assert calls == ["a"]  # b never ran


def test_composite_strategy_unknown_subtask_raises(tmp_path: Path) -> None:
    reg = PluginRegistry()
    strategy = CompositeStrategy(subtasks=("missing",), registry=reg)
    with pytest.raises(KeyError, match="missing"):
        strategy.execute(args=(), cwd=tmp_path)
