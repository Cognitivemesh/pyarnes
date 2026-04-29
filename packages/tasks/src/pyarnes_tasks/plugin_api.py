"""Public types for the plugin architecture.

`TaskKind` selects the execution strategy. `TaskSpec` is the serialised
view of a registered plugin — used by ``--help``, JSONL event payloads,
and read-only registry inspection.

Authors do **not** write `TaskSpec` literals. They subclass `Plugin`
(see :mod:`pyarnes_tasks.plugin_base`) and the base class derives the
spec from class attributes via :meth:`Plugin.to_spec`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import NotRequired, TypedDict


class TaskKind(StrEnum):
    """How a plugin's body is dispatched."""

    SHELL = "shell"  # subprocess.run of an installed CLI
    SCRIPT = "script"  # `uv run <file>` honouring the file's PEP 723 block
    MODULE = "module"  # in-process call into the parent venv
    COMPOSITE = "composite"  # ordered fan-out to other registered tasks


class TaskSpec(TypedDict):
    """Serialised view of a plugin. Built by ``Plugin.to_spec``."""

    name: str
    kind: TaskKind
    description: NotRequired[str]
    cmd: NotRequired[list[str]]
    targets: NotRequired[list[str]]
    subtasks: NotRequired[list[str]]
    requires_bin: NotRequired[list[str]]
    accepts_no_tests: NotRequired[bool]


__all__ = ["TaskKind", "TaskSpec"]
