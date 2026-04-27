"""Rule-based task classification (13 buckets).

Pure-functional classifier — no LLM call, no I/O. Walks a sequence of
``ToolCallEntry`` records and assigns each one a :class:`TaskKind`.
The rules look at:

1. The canonical tool label (``Bash``, ``Edit``, …).
2. The shape of the arguments (e.g. ``git`` prefix on a Bash command).
3. The window of neighbouring calls — Edit→Bash→Edit collapses to
   :data:`TaskKind.DEBUGGING` rather than :data:`TaskKind.CODING`.

Buckets follow the CodeBurn taxonomy: every call must end up in
exactly one bucket so per-bucket cost sums equal total cost.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum
from typing import Final

from pyarnes_bench.burn.normalize import normalize_tool
from pyarnes_harness.capture.tool_log import ToolCallEntry

__all__ = [
    "TaskKind",
    "classify",
    "classify_window",
]


class TaskKind(Enum):
    """Coarse activity buckets for one or many tool calls."""

    CODING = "coding"
    DEBUGGING = "debugging"
    FEATURE_DEV = "feature_dev"
    REFACTOR = "refactor"
    TESTING = "testing"
    EXPLORATION = "exploration"
    PLANNING = "planning"
    DELEGATION = "delegation"
    GIT_OPS = "git_ops"
    BUILD_DEPLOY = "build_deploy"
    BRAINSTORM = "brainstorm"
    CONVERSATION = "conversation"
    GENERAL = "general"


_GIT_PREFIXES: Final[tuple[str, ...]] = ("git ", "git-", "gh ", "gh-")
_TEST_TOKENS: Final[tuple[str, ...]] = ("pytest", "jest", " test", "tox", "phpunit", "vitest", "mocha")
_BUILD_TOKENS: Final[tuple[str, ...]] = (
    "make ",
    "make\t",
    "cmake",
    "docker",
    "kubectl",
    "terraform",
    "gradle",
    "mvn ",
    "npm run build",
    "yarn build",
    "uv build",
    "pip install",
    "uv sync",
    "uv pip",
)
_REFACTOR_TOKENS: Final[tuple[str, ...]] = ("rename", "refactor", "extract", "inline")


def _bash_command(entry: ToolCallEntry) -> str:
    raw = entry.arguments.get("command") if isinstance(entry.arguments, dict) else None
    return raw.lower() if isinstance(raw, str) else ""


_DIRECT_TOOL_KIND: Final[dict[str, TaskKind]] = {
    "Task": TaskKind.DELEGATION,
    "TodoWrite": TaskKind.PLANNING,
    "TodoRead": TaskKind.PLANNING,
    "ExitPlanMode": TaskKind.PLANNING,
    "WebFetch": TaskKind.EXPLORATION,
    "WebSearch": TaskKind.EXPLORATION,
    "Read": TaskKind.EXPLORATION,
    "Grep": TaskKind.EXPLORATION,
    "Glob": TaskKind.EXPLORATION,
    "Write": TaskKind.FEATURE_DEV,
    "NotebookEdit": TaskKind.CODING,
    "MCP": TaskKind.CODING,
}


def classify(entry: ToolCallEntry) -> TaskKind:
    """Return the :class:`TaskKind` for one isolated call.

    Used when no surrounding window is available (e.g. a one-call
    session). For full sessions, prefer :func:`classify_window` —
    contextual buckets like :data:`TaskKind.DEBUGGING` need neighbours.
    """
    tool = normalize_tool(entry.tool)
    direct = _DIRECT_TOOL_KIND.get(tool)
    if direct is not None:
        return direct
    if tool == "Bash":
        return _classify_bash(entry)
    if tool == "Edit":
        return _classify_edit(entry)
    return TaskKind.GENERAL


def _classify_bash(entry: ToolCallEntry) -> TaskKind:
    cmd = _bash_command(entry)
    if not cmd:
        return TaskKind.GENERAL
    if cmd.startswith(_GIT_PREFIXES):
        return TaskKind.GIT_OPS
    if any(tok in cmd for tok in _TEST_TOKENS):
        return TaskKind.TESTING
    if any(tok in cmd for tok in _BUILD_TOKENS):
        return TaskKind.BUILD_DEPLOY
    return TaskKind.CODING


def _classify_edit(entry: ToolCallEntry) -> TaskKind:
    args = entry.arguments if isinstance(entry.arguments, dict) else {}
    blob = " ".join(
        v.lower()
        for v in args.values()
        if isinstance(v, str)
    )
    if any(tok in blob for tok in _REFACTOR_TOKENS):
        return TaskKind.REFACTOR
    return TaskKind.CODING


def classify_window(entries: Sequence[ToolCallEntry]) -> list[TaskKind]:
    """Classify each entry, upgrading buckets that need context.

    The single-call rules in :func:`classify` are the baseline. We then
    walk the window and re-tag a few patterns:

    * **Edit → failing Bash → Edit on same file** — debugging loop, all
      three calls become :data:`TaskKind.DEBUGGING`.
    * **Three or more consecutive Reads without an Edit** — pure
      exploration; already covered by the per-call rule but reinforced
      so a subsequent Edit doesn't re-tag the run.
    """
    base = [classify(e) for e in entries]
    n = len(entries)
    for idx in range(n - 2):
        first, mid, last = entries[idx], entries[idx + 1], entries[idx + 2]
        if (
            normalize_tool(first.tool) == "Edit"
            and normalize_tool(mid.tool) == "Bash"
            and mid.is_error
            and normalize_tool(last.tool) == "Edit"
            and _same_file(first, last)
        ):
            base[idx] = TaskKind.DEBUGGING
            base[idx + 1] = TaskKind.DEBUGGING
            base[idx + 2] = TaskKind.DEBUGGING
    return base


def _same_file(a: ToolCallEntry, b: ToolCallEntry) -> bool:
    """Return True when two Edit calls touch the same ``file_path``."""
    pa = a.arguments.get("file_path") if isinstance(a.arguments, dict) else None
    pb = b.arguments.get("file_path") if isinstance(b.arguments, dict) else None
    return isinstance(pa, str) and isinstance(pb, str) and pa == pb
