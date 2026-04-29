"""Tests for the plugin loader — discovery, registration, plugin_file attach."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyarnes_tasks.plugin_loader import load_plugins
from pyarnes_tasks.registry import global_registry


@pytest.fixture(autouse=True)
def _isolate_global_registry():
    snapshot = global_registry().as_dict()
    global_registry().clear()
    yield
    global_registry().clear()
    for name, plugin in snapshot.items():
        global_registry().register(name, plugin)


def _write(plugins_dir: Path, name: str, body: str) -> Path:
    file = plugins_dir / name
    file.write_text(body)
    return file


def test_loader_imports_every_py_file(tmp_path: Path) -> None:
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    _write(
        plugins,
        "demo.py",
        "from pyarnes_tasks.plugin_base import ModulePlugin\n"
        "class Demo(ModulePlugin):\n"
        "    name = 'demo:loaded'\n"
        "    def call(self, argv):\n"
        "        return 0\n",
    )
    load_plugins(plugins)
    assert "demo:loaded" in global_registry()


def test_loader_skips_underscore_prefixed_files(tmp_path: Path) -> None:
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    _write(
        plugins,
        "_helper.py",
        "from pyarnes_tasks.plugin_base import ModulePlugin\n"
        "class Helper(ModulePlugin):\n"
        "    name = 'should:not:appear'\n"
        "    def call(self, argv):\n"
        "        return 0\n",
    )
    load_plugins(plugins)
    assert "should:not:appear" not in global_registry()


def test_loader_attaches_plugin_file_to_script_plugins(tmp_path: Path) -> None:
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    file = _write(
        plugins,
        "demo_script.py",
        "from pyarnes_tasks.plugin_base import ScriptPlugin\n"
        "class DemoScript(ScriptPlugin):\n"
        "    name = 'demo:script'\n"
        "    def run_script(self, argv):\n"
        "        return 0\n",
    )
    load_plugins(plugins)
    plugin = global_registry().get("demo:script")
    assert plugin is not None
    assert plugin.plugin_file == file


def test_loader_handles_missing_directory(tmp_path: Path) -> None:
    # Loader should be a no-op (not crash) when the plugin directory is missing.
    load_plugins(tmp_path / "does_not_exist")
    # No crash, no plugins registered.


def test_loader_handles_empty_directory(tmp_path: Path) -> None:
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    load_plugins(plugins)
    assert len(global_registry()) == 0


def test_loader_imports_files_in_sorted_order(tmp_path: Path) -> None:
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    _write(
        plugins,
        "z_last.py",
        "from pyarnes_tasks.plugin_base import ModulePlugin\n"
        "class Z(ModulePlugin):\n"
        "    name = 'z'\n"
        "    def call(self, argv): return 0\n",
    )
    _write(
        plugins,
        "a_first.py",
        "from pyarnes_tasks.plugin_base import ModulePlugin\n"
        "class A(ModulePlugin):\n"
        "    name = 'a'\n"
        "    def call(self, argv): return 0\n",
    )
    load_plugins(plugins)
    assert global_registry().names == ["a", "z"]
