"""Tests for the Plugin ABC and four kind-specific base classes.

Covers: auto-registration, observability events, perf timing, error
taxonomy mapping, requires-bin preflight, pytest exit-5 special case.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from pyarnes_core.errors import UnexpectedError, UserFixableError
from pyarnes_tasks.plugin_api import TaskKind
from pyarnes_tasks.plugin_base import (
    CompositePlugin,
    ModulePlugin,
    Plugin,
    ScriptPlugin,
    ShellPlugin,
)
from pyarnes_tasks.registry import global_registry


@pytest.fixture(autouse=True)
def _isolate_global_registry():
    """Clear the global registry between tests so subclasses don't leak."""
    snapshot = global_registry().as_dict()
    global_registry().clear()
    yield
    global_registry().clear()
    for name, plugin in snapshot.items():
        global_registry().register(name, plugin)


# ── Auto-registration ────────────────────────────────────────────────────


def test_subclass_auto_registers() -> None:
    class Demo(ModulePlugin):
        name = "demo"

        def call(self, argv: list[str]) -> int:
            return 0

    assert "demo" in global_registry()
    assert isinstance(global_registry().get("demo"), Demo)


def test_abstract_kind_base_does_not_register() -> None:
    # Re-import the module: the four kind-base classes must NOT be in the
    # registry — they're authoring scaffolding, not real plugins.
    assert "ShellPlugin" not in global_registry()
    assert "ScriptPlugin" not in global_registry()
    assert "ModulePlugin" not in global_registry()
    assert "CompositePlugin" not in global_registry()


def test_subclass_without_name_does_not_register() -> None:
    class _Mixin(ModulePlugin):
        # No `name` set → loader-internal helper / mixin → skip registration.
        abstract = True

        def call(self, argv: list[str]) -> int:
            return 0

    assert len(global_registry()) == 0


# ── Lifecycle: observability + perf ─────────────────────────────────────


def test_run_emits_started_and_finished_events(tmp_path: Path) -> None:
    class Demo(ModulePlugin):
        name = "demo:obs"

        def call(self, argv: list[str]) -> int:
            return 0

    plugin = global_registry().get("demo:obs")
    with patch("pyarnes_tasks.plugin_base.log_event") as log:
        plugin.run((), tmp_path)
    events = [call.args[1] for call in log.call_args_list]
    assert "plugin.started" in events
    assert "plugin.finished" in events


def test_run_records_wall_time(tmp_path: Path) -> None:
    class Demo(ModulePlugin):
        name = "demo:wall"

        def call(self, argv: list[str]) -> int:
            return 0

    plugin = global_registry().get("demo:wall")
    with patch("pyarnes_tasks.plugin_base.log_event") as log:
        plugin.run((), tmp_path)
    finished = [c for c in log.call_args_list if c.args[1] == "plugin.finished"]
    assert finished, "expected a plugin.finished event"
    fields = finished[0].kwargs
    assert "wall_ms" in fields
    assert isinstance(fields["wall_ms"], int)
    assert fields["wall_ms"] >= 0


# ── Error taxonomy ──────────────────────────────────────────────────────


def test_unhandled_exception_maps_to_unexpected_error(tmp_path: Path) -> None:
    class Demo(ModulePlugin):
        name = "demo:boom"

        def call(self, argv: list[str]) -> int:
            msg = "kaboom"
            raise ValueError(msg)

    plugin = global_registry().get("demo:boom")
    with pytest.raises(UnexpectedError, match="kaboom"):
        plugin.run((), tmp_path)


def test_user_fixable_error_propagates(tmp_path: Path) -> None:
    class Demo(ModulePlugin):
        name = "demo:user"

        def call(self, argv: list[str]) -> int:
            raise UserFixableError("install foo")

    plugin = global_registry().get("demo:user")
    with pytest.raises(UserFixableError):
        plugin.run((), tmp_path)


# ── requires_bin preflight ──────────────────────────────────────────────


def test_missing_required_binary_raises_user_fixable(tmp_path: Path) -> None:
    class Demo(ModulePlugin):
        name = "demo:requires"
        requires_bin = ("definitely-not-real-xyz",)

        def call(self, argv: list[str]) -> int:
            return 0

    plugin = global_registry().get("demo:requires")
    with pytest.raises(UserFixableError, match="definitely-not-real-xyz"):
        plugin.run((), tmp_path)


# ── pytest exit-5 ───────────────────────────────────────────────────────


def test_accepts_no_tests_remaps_exit_5(tmp_path: Path) -> None:
    class Demo(ModulePlugin):
        name = "demo:notests"
        accepts_no_tests = True

        def call(self, argv: list[str]) -> int:
            return 5

    plugin = global_registry().get("demo:notests")
    assert plugin.run((), tmp_path) == 0


def test_default_does_not_remap_exit_5(tmp_path: Path) -> None:
    class Demo(ModulePlugin):
        name = "demo:strict"

        def call(self, argv: list[str]) -> int:
            return 5

    plugin = global_registry().get("demo:strict")
    assert plugin.run((), tmp_path) == 5


# ── to_spec serialisation ──────────────────────────────────────────────


def test_to_spec_round_trip() -> None:
    class Demo(ShellPlugin):
        name = "demo:spec"
        description = "demo desc"
        cmd = ("echo", "hi")
        targets = ("sources",)
        requires_bin = ("echo",)

    spec = global_registry().get("demo:spec").to_spec()
    assert spec["name"] == "demo:spec"
    assert spec["kind"] == TaskKind.SHELL
    assert spec["description"] == "demo desc"
    assert spec["cmd"] == ["echo", "hi"]
    assert spec["targets"] == ["sources"]
    assert spec["requires_bin"] == ["echo"]


# ── Composite plumbing ─────────────────────────────────────────────────


def test_composite_runs_subtasks_in_order(tmp_path: Path) -> None:
    order: list[str] = []

    class A(ModulePlugin):
        name = "a"

        def call(self, argv: list[str]) -> int:
            order.append("a")
            return 0

    class B(ModulePlugin):
        name = "b"

        def call(self, argv: list[str]) -> int:
            order.append("b")
            return 0

    class Both(CompositePlugin):
        name = "both"
        subtasks = ("a", "b")

    global_registry().get("both").run((), tmp_path)
    assert order == ["a", "b"]


# ── Plugin (ABC) is not instantiable ───────────────────────────────────


def test_plugin_is_abstract() -> None:
    with pytest.raises(TypeError):
        Plugin()  # type: ignore[abstract]


# Reference to keep ScriptPlugin import live until SCRIPT-kind tests land.
_ = ScriptPlugin
