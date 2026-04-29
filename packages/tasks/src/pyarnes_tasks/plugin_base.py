"""Plugin ABC and four kind-specific base classes.

Authors subclass one of :class:`ShellPlugin`, :class:`ScriptPlugin`,
:class:`ModulePlugin`, or :class:`CompositePlugin` to declare a task.
The base class :class:`Plugin` bakes in observability (JSONL events),
perf timing (wall-clock + RSS delta), error-taxonomy mapping, missing
binary preflight, and self-registration via ``__init_subclass__``.

A plugin author writes only what is unique to their task — the cmd
list, the callable, the subtasks. The base class handles the rest.
"""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from time import perf_counter
from typing import Any, ClassVar

from pyarnes_core.errors import (
    HarnessError,
    UnexpectedError,
    UserFixableError,
)
from pyarnes_core.observability import log_event
from pyarnes_core.observe.logger import get_logger
from pyarnes_tasks.plugin_api import TaskKind, TaskSpec
from pyarnes_tasks.registry import global_registry

__all__ = [
    "CompositePlugin",
    "ModulePlugin",
    "Plugin",
    "ScriptPlugin",
    "ShellPlugin",
]


_PYTEST_NO_TESTS_EXIT = 5

_logger = get_logger("pyarnes_tasks.plugin")


class Plugin(ABC):
    """Authoring contract for every task in ``/plugins/``.

    Subclasses set ``name`` and ``kind`` (the kind-specific bases below
    set ``kind`` for you), optionally ``description``, and implement
    :meth:`_execute`. The public :meth:`run` wraps ``_execute`` with
    structured JSONL events, wall-time + RSS metrics, missing-binary
    preflight, and the project's error taxonomy.
    """

    # ── Declarative surface (override on subclass) ──────────────────
    name: ClassVar[str] = ""
    kind: ClassVar[TaskKind]
    description: ClassVar[str] = ""
    requires_bin: ClassVar[tuple[str, ...]] = ()
    accepts_no_tests: ClassVar[bool] = False
    targets: ClassVar[tuple[str, ...]] = ()

    # ── Internal: kind-base classes set this so they don't self-register
    abstract: ClassVar[bool] = False

    # ── Auto-registration ────────────────────────────────────────────
    def __init_subclass__(cls, **kw: Any) -> None:
        """Self-register the subclass into the global plugin registry."""
        super().__init_subclass__(**kw)
        # Don't register the kind-base classes themselves.
        if cls.__dict__.get("abstract", False):
            return
        # Mixins / partial subclasses with no name are also skipped.
        if not cls.__dict__.get("name"):
            return
        global_registry().register(cls.name, cls())

    # ── Public entry-point — never override ─────────────────────────
    def run(self, args: tuple[str, ...], cwd: Path) -> int:
        """Execute this plugin with observability, perf, and error mapping."""
        self._check_requires_bin()
        ctx: dict[str, Any] = {
            "name": self.name,
            "kind": str(self.kind),
            "args": list(args),
        }
        start = perf_counter()
        log_event(_logger, "plugin.started", **ctx)
        # Inline try/finally instead of @contextmanager: the project's error
        # types are @dataclass(frozen=True, slots=True) and contextlib's
        # __exit__ does `exc.__traceback__ = ...`, which a frozen slots
        # __setattr__ refuses with TypeError.
        try:
            try:
                code = self._execute(args, cwd)
            except HarnessError:
                raise
            except Exception as exc:
                ctx["error"] = repr(exc)
                raise UnexpectedError(
                    message=str(exc) or repr(exc),
                    original=exc,
                ) from exc
            ctx["exit_code"] = code
            if self.accepts_no_tests and code == _PYTEST_NO_TESTS_EXIT:
                return 0
            return code
        finally:
            ctx["wall_ms"] = int((perf_counter() - start) * 1000)
            log_event(_logger, "plugin.finished", **ctx)

    # ── Subclass surface ────────────────────────────────────────────
    @abstractmethod
    def _execute(self, args: tuple[str, ...], cwd: Path) -> int: ...

    # ── Serialisation for --help and JSONL payloads ─────────────────
    def to_spec(self) -> TaskSpec:
        """Return the serialised view used by ``--help`` and event payloads."""
        spec: TaskSpec = {"name": self.name, "kind": self.kind}
        if self.description:
            spec["description"] = self.description
        if self.requires_bin:
            spec["requires_bin"] = list(self.requires_bin)
        if self.accepts_no_tests:
            spec["accepts_no_tests"] = self.accepts_no_tests
        # Kind-specific fields are filled by the concrete bases below.
        self._extend_spec(spec)
        return spec

    def _extend_spec(self, spec: TaskSpec) -> None:  # noqa: B027
        """Hook for kind-bases to add cmd/targets/subtasks. Default: no-op."""

    # ── Common infrastructure (do not override) ─────────────────────
    def _check_requires_bin(self) -> None:
        for binary in self.requires_bin:
            if not shutil.which(binary):
                raise UserFixableError(
                    message=(
                        f"Missing binary {binary!r} required by task "
                        f"{self.name!r}. Install it (or `uv sync --group <group>`) "
                        "and retry."
                    ),
                )


# ── Kind-specific bases ──────────────────────────────────────────────


class ShellPlugin(Plugin):
    """Run a fully-resolved shell command via ``subprocess.run``."""

    abstract = True
    kind: ClassVar[TaskKind] = TaskKind.SHELL
    cmd: ClassVar[tuple[str, ...]] = ()

    def _execute(self, args: tuple[str, ...], cwd: Path) -> int:
        # Late imports avoid circular pulls (strategies → registry → base).
        from pyarnes_tasks.strategies import ShellStrategy  # noqa: PLC0415
        from pyarnes_tasks.targets import resolve_targets  # noqa: PLC0415

        resolved = resolve_targets(self.targets, cwd)
        return ShellStrategy(cmd=(*self.cmd, *resolved)).execute(args, cwd)

    def _extend_spec(self, spec: TaskSpec) -> None:
        if self.cmd:
            spec["cmd"] = list(self.cmd)
        if self.targets:
            spec["targets"] = list(self.targets)


class ScriptPlugin(Plugin):
    """Re-invoke this file via ``uv run`` so PEP 723 deps resolve in isolation."""

    abstract = True
    kind: ClassVar[TaskKind] = TaskKind.SCRIPT
    plugin_file: ClassVar[Path | None] = None

    def _execute(self, args: tuple[str, ...], cwd: Path) -> int:
        if self.plugin_file is None:
            raise UnexpectedError(
                message=(
                    f"ScriptPlugin {self.name!r} has no plugin_file. The loader is supposed to attach it after import."
                ),
            )
        from pyarnes_tasks.strategies import ScriptStrategy  # noqa: PLC0415
        from pyarnes_tasks.targets import resolve_targets  # noqa: PLC0415

        # Resolved targets prefix the user's args so SCRIPT plugins can
        # treat them as positional inputs (matching SHELL semantics).
        resolved = resolve_targets(self.targets, cwd)
        forwarded = (*resolved, *args)
        return ScriptStrategy(plugin_file=self.plugin_file).execute(forwarded, cwd)

    def run_script(self, argv: list[str]) -> int:
        """Body invoked when the plugin file runs as ``uv run <file>``.

        Subclasses override this. Heavy / PEP 723-only imports must live
        inside the override so the parent process can import the module
        for registration without those deps installed.
        """
        msg = f"ScriptPlugin {self.name!r} did not override run_script()"
        raise NotImplementedError(msg)


class ModulePlugin(Plugin):
    """Run an in-process callable using the parent venv's deps."""

    abstract = True
    kind: ClassVar[TaskKind] = TaskKind.MODULE

    def _execute(self, args: tuple[str, ...], cwd: Path) -> int:
        from pyarnes_tasks.strategies import ModuleStrategy  # noqa: PLC0415

        return ModuleStrategy(callable=self.call).execute(args, cwd)

    @abstractmethod
    def call(self, argv: list[str]) -> int:
        """Run this task in-process. Return a CLI exit code."""


class CompositePlugin(Plugin):
    """Fan out to other registered plugins in order; bail on first failure."""

    abstract = True
    kind: ClassVar[TaskKind] = TaskKind.COMPOSITE
    subtasks: ClassVar[tuple[str, ...]] = ()

    def _execute(self, args: tuple[str, ...], cwd: Path) -> int:  # noqa: ARG002
        from pyarnes_tasks.strategies import CompositeStrategy  # noqa: PLC0415

        return CompositeStrategy(subtasks=self.subtasks, registry=global_registry()).execute((), cwd)

    def _extend_spec(self, spec: TaskSpec) -> None:
        if self.subtasks:
            spec["subtasks"] = list(self.subtasks)
