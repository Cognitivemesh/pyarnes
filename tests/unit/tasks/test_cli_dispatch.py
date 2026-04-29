"""Tests for the cli dispatch — registry takes precedence over the legacy dict."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

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


def test_registry_takes_precedence_over_legacy_dict(tmp_path: Path) -> None:
    calls: list[str] = []

    class FakeLint(ModulePlugin):
        name = "lint"

        def call(self, argv: list[str]) -> int:
            calls.append("plugin")
            _ = argv
            return 0

    legacy = {"lint": ["echo", "legacy"]}
    code = cli._dispatch("lint", legacy, tmp_path, extra=())
    assert code == 0
    assert calls == ["plugin"]


def test_falls_back_to_legacy_dict_when_no_plugin(tmp_path: Path) -> None:
    legacy = {"lint": ["echo", "legacy"]}
    with patch("pyarnes_tasks.cli.subprocess.run") as run:
        run.return_value.returncode = 0
        code = cli._dispatch("lint", legacy, tmp_path, extra=())
    assert code == 0
    run.assert_called_once()


def test_unknown_task_returns_nonzero(tmp_path: Path) -> None:
    code = cli._dispatch("does-not-exist", {}, tmp_path, extra=())
    assert code != 0
