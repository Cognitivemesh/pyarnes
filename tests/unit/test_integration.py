"""End-to-end integration tests for the AgentLoop runtime path.

Covers async concurrency, lifecycle FSM integration, and monorepo package
import validation — scenarios that fall outside the BDD feature files.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from pyarnes_core.lifecycle import Lifecycle, Phase
from pyarnes_core.types import ModelClient, ToolHandler
from pyarnes_harness.loop import AgentLoop

# ── Shared helpers ─────────────────────────────────────────────────────────


@dataclass
class _ScriptedModel(ModelClient):
    actions: list[dict[str, Any]]
    _idx: int = 0

    async def next_action(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        action = self.actions[self._idx]
        self._idx += 1
        return action


@dataclass
class _LabeledTool(ToolHandler):
    label: str

    async def execute(self, arguments: dict[str, Any]) -> Any:
        return self.label


def _one_shot_loop(label: str) -> AgentLoop:
    model = _ScriptedModel(
        actions=[
            {"type": "tool_call", "tool": "t", "id": "x1", "arguments": {}},
            {"type": "final_answer", "content": "done"},
        ]
    )
    return AgentLoop(tools={"t": _LabeledTool(label)}, model=model)


# ── Tests ──────────────────────────────────────────────────────────────────


async def test_two_loops_run_concurrently() -> None:
    """Two independent loops complete without interference when gathered."""
    loop_a = _one_shot_loop("result-a")
    loop_b = _one_shot_loop("result-b")

    results_a, results_b = await asyncio.gather(loop_a.run([]), loop_b.run([]))

    tools_a = [m for m in results_a if m.get("role") == "tool"]
    tools_b = [m for m in results_b if m.get("role") == "tool"]
    assert tools_a[0]["content"] == "result-a"
    assert tools_b[0]["content"] == "result-b"


def test_lifecycle_transitions_alongside_loop() -> None:
    """Lifecycle FSM can be driven manually around a loop run."""
    lc = Lifecycle()
    model = _ScriptedModel(actions=[{"type": "final_answer", "content": "done"}])
    loop = AgentLoop(tools={}, model=model)

    lc.start()
    asyncio.run(loop.run([]))
    lc.complete()

    assert lc.phase == Phase.COMPLETED
    assert lc.is_terminal
    assert len(lc.history) == 2


def test_all_workspace_packages_importable() -> None:
    """All pyarnes workspace packages resolve and expose their __name__.

    Imports are intentionally local so a missing workspace package
    surfaces as a test failure, not a collection-time error.
    """
    import pyarnes_bench  # noqa: PLC0415
    import pyarnes_core  # noqa: PLC0415
    import pyarnes_guardrails  # noqa: PLC0415
    import pyarnes_harness  # noqa: PLC0415
    import pyarnes_tasks  # noqa: PLC0415

    assert pyarnes_core.__name__ == "pyarnes_core"
    assert pyarnes_harness.__name__ == "pyarnes_harness"
    assert pyarnes_guardrails.__name__ == "pyarnes_guardrails"
    assert pyarnes_bench.__name__ == "pyarnes_bench"
    assert pyarnes_tasks.__name__ == "pyarnes_tasks"
