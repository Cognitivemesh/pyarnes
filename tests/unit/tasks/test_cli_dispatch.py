"""Tests for the cli dispatch — registry-only path."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyarnes_tasks import cli
from pyarnes_tasks.plugin_base import ModulePlugin
from pyarnes_tasks.registry import global_registry


@pytest.fixture(autouse=True)
def _isolate_global_registry():
    snapshot = global_registry().as_dict()
    global_registry().clear()
    yield
    global_registry().clear()
    for name, plugin in snapshot.items():
        global_registry().register(name, plugin)


def test_dispatch_runs_registered_plugin(tmp_path: Path) -> None:
    calls: list[str] = []

    class Lint(ModulePlugin):
        name = "lint"

        def call(self, argv: list[str]) -> int:
            _ = argv
            calls.append("plugin")
            return 0

    code = cli._dispatch("lint", tmp_path, extra=())
    assert code == 0
    assert calls == ["plugin"]


def test_dispatch_unknown_task_returns_nonzero(tmp_path: Path) -> None:
    code = cli._dispatch("does-not-exist", tmp_path, extra=())
    assert code != 0


def test_dispatch_forwards_extra_args(tmp_path: Path) -> None:
    captured: dict = {}

    class Lint(ModulePlugin):
        name = "lint"

        def call(self, argv: list[str]) -> int:
            captured["argv"] = argv
            return 0

    cli._dispatch("lint", tmp_path, extra=("--fix", "x"))
    assert captured["argv"] == ["--fix", "x"]
