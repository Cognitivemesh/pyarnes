"""Internal execution strategies — one per :class:`TaskKind`.

Plugin authors do not interact with these directly. The kind-specific
base classes in :mod:`pyarnes_tasks.plugin_base` instantiate the right
strategy in their ``_execute`` method. Strategies stay separate so they
can be unit-tested in isolation against fake commands and registries.
"""

from __future__ import annotations

import subprocess  # nosec B404 — every command is built from in-tree config
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyarnes_tasks.registry import PluginRegistry


__all__ = [
    "CompositeStrategy",
    "ModuleStrategy",
    "ScriptStrategy",
    "ShellStrategy",
]


@dataclass(frozen=True, slots=True)
class ShellStrategy:
    """Run a fully-resolved command line via ``subprocess.run``."""

    cmd: tuple[str, ...]

    def execute(self, args: tuple[str, ...], cwd: Path) -> int:
        """Run ``cmd + args`` via subprocess; return its exit code."""
        try:
            return subprocess.run(  # noqa: S603  # nosec B603
                [*self.cmd, *args], check=False, cwd=cwd
            ).returncode
        except FileNotFoundError as exc:
            print(  # noqa: T201
                f"Command skipped — missing binary: {exc.filename}",
                file=sys.stderr,
            )
            return 127


@dataclass(frozen=True, slots=True)
class ScriptStrategy:
    """Re-invoke a PEP 723 plugin file under ``uv run`` for dep isolation."""

    plugin_file: Path

    def execute(self, args: tuple[str, ...], cwd: Path) -> int:
        """Re-invoke the plugin file under ``uv run`` so PEP 723 deps resolve."""
        # `uv` resolved from PATH is intentional — uv is the project's hard
        # dependency, not user input.
        try:
            cmd = ["uv", "run", str(self.plugin_file), *args]
            return subprocess.run(cmd, check=False, cwd=cwd).returncode  # noqa: S603
        except FileNotFoundError as exc:
            print(  # noqa: T201
                f"`uv` not on PATH ({exc.filename}). Install uv to run SCRIPT plugins.",
                file=sys.stderr,
            )
            return 127


@dataclass(frozen=True, slots=True)
class ModuleStrategy:
    """Call an in-process function with the parent venv's deps available."""

    callable: Callable[[list[str]], int]

    def execute(self, args: tuple[str, ...], cwd: Path) -> int:  # noqa: ARG002
        """Invoke the callable with ``args``; ``cwd`` is unused here."""
        return self.callable(list(args))


@dataclass(frozen=True, slots=True)
class CompositeStrategy:
    """Run a sequence of registered plugins in order; bail on first failure."""

    subtasks: tuple[str, ...]
    registry: PluginRegistry

    def execute(self, args: tuple[str, ...], cwd: Path) -> int:  # noqa: ARG002
        """Run each subtask in order; return the first non-zero exit code."""
        for sub in self.subtasks:
            plugin = self.registry.get(sub)
            if plugin is None:
                msg = f"Composite refers to unknown subtask {sub!r}"
                raise KeyError(msg)
            code = plugin.run((), cwd)
            if code != 0:
                return code
        return 0
