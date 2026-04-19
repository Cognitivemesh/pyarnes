"""BDD step definitions for AgentLoop full runtime path validation."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pytest_bdd import given, scenario, then, when

from pyarnes_core.errors import TransientError, UserFixableError
from pyarnes_core.types import ModelClient, ToolHandler
from pyarnes_guardrails import PathGuardrail
from pyarnes_harness.capture.tool_log import ToolCallLogger
from pyarnes_harness.loop import AgentLoop, LoopConfig


# ── Scenarios ──────────────────────────────────────────────────────────────


@scenario("../feature_validation.feature", "Flaky tool is retried the exact configured number of times")
def test_flaky_tool_retry() -> None:
    """Flaky tool is retried the exact configured number of times."""


@scenario("../feature_validation.feature", "ToolCallLogger records every invocation as valid JSONL")
def test_tool_call_logger_jsonl() -> None:
    """ToolCallLogger records every invocation as valid JSONL."""


@scenario(
    "../feature_validation.feature",
    "Guardrail enforced inside ToolHandler propagates as UserFixableError",
)
def test_guardrail_in_loop() -> None:
    """Guardrail enforced inside ToolHandler propagates as UserFixableError."""


# ── Shared helpers ─────────────────────────────────────────────────────────


@dataclass
class _ScriptedModel(ModelClient):
    actions: list[dict[str, Any]]
    _idx: int = 0

    async def next_action(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        action = self.actions[self._idx]
        self._idx += 1
        return action


# ── Retry scenario ─────────────────────────────────────────────────────────


@dataclass
class _FlakeyTool(ToolHandler):
    fail_times: int
    call_count: int = 0

    async def execute(self, arguments: dict[str, Any]) -> Any:
        self.call_count += 1
        if self.call_count <= self.fail_times:
            raise TransientError(message="temp failure")
        return "ok"


@given("a flaky tool that fails twice then succeeds", target_fixture="retry_ctx")
def _given_flaky_tool() -> dict[str, Any]:
    return {"tool": _FlakeyTool(fail_times=2), "loop": None, "result": None, "exc": None}


@given("an integration loop with max_retries 2")
def _given_retry_loop(retry_ctx: dict[str, Any]) -> None:
    model = _ScriptedModel(
        actions=[
            {"type": "tool_call", "tool": "flaky", "id": "r1", "arguments": {}},
            {"type": "final_answer", "content": "done"},
        ]
    )
    retry_ctx["loop"] = AgentLoop(
        tools={"flaky": retry_ctx["tool"]},
        model=model,
        config=LoopConfig(max_retries=2, retry_base_delay=0.0),
    )


@when("I run the integration loop")
def _when_run_integration(retry_ctx: dict[str, Any]) -> None:
    try:
        retry_ctx["result"] = asyncio.run(retry_ctx["loop"].run([]))
    except Exception as exc:  # noqa: BLE001
        retry_ctx["exc"] = exc


@then("the tool execute method was called 3 times")
def _then_called_three_times(retry_ctx: dict[str, Any]) -> None:
    assert retry_ctx["tool"].call_count == 3


@then("the loop returns a successful tool message")
def _then_successful_result(retry_ctx: dict[str, Any]) -> None:
    tool_msgs = [m for m in retry_ctx["result"] if m.get("role") == "tool"]
    assert any(not m.get("is_error") for m in tool_msgs)


# ── Logger scenario ────────────────────────────────────────────────────────


@dataclass
class _SimpleTool(ToolHandler):
    async def execute(self, arguments: dict[str, Any]) -> Any:
        return "pong"


@given("an integration loop with a ToolCallLogger and a simple tool", target_fixture="logger_ctx")
def _given_logger_loop(tmp_path: Path) -> dict[str, Any]:
    log_file = tmp_path / "calls.jsonl"
    tcl = ToolCallLogger(log_file)
    model = _ScriptedModel(
        actions=[
            {"type": "tool_call", "tool": "ping", "id": "l1", "arguments": {}},
            {"type": "final_answer", "content": "done"},
        ]
    )
    loop = AgentLoop(
        tools={"ping": _SimpleTool()},
        model=model,
        tool_call_logger=tcl,
    )
    return {"loop": loop, "logger": tcl, "log_file": log_file, "result": None}


@when("I run the logged integration loop")
def _when_run_logged(logger_ctx: dict[str, Any]) -> None:
    tcl: ToolCallLogger = logger_ctx["logger"]
    with tcl:
        logger_ctx["result"] = asyncio.run(logger_ctx["loop"].run([]))


@then("the log file contains 1 line")
def _then_one_log_line(logger_ctx: dict[str, Any]) -> None:
    lines = logger_ctx["log_file"].read_text().strip().splitlines()
    assert len(lines) == 1


@then("the log line has required JSONL keys")
def _then_jsonl_schema(logger_ctx: dict[str, Any]) -> None:
    raw = logger_ctx["log_file"].read_text().strip().splitlines()[0]
    entry = json.loads(raw)
    for key in ("tool", "result", "started_at", "finished_at", "duration_seconds"):
        assert key in entry


# ── Guardrail scenario ─────────────────────────────────────────────────────


@dataclass
class _GuardedTool(ToolHandler):
    guardrail: PathGuardrail = field(
        default_factory=lambda: PathGuardrail(allowed_roots=("/workspace",))
    )

    async def execute(self, arguments: dict[str, Any]) -> Any:
        self.guardrail.check("guarded", arguments)
        return "safe"


@given("a tool that enforces a PathGuardrail on its input path", target_fixture="guard_loop_ctx")
def _given_guarded_tool() -> dict[str, Any]:
    return {"tool": _GuardedTool(), "result": None, "exc": None}


@when("I run the guarded integration loop with a blocked path")
def _when_run_guarded(guard_loop_ctx: dict[str, Any]) -> None:
    model = _ScriptedModel(
        actions=[
            {"type": "tool_call", "tool": "guarded", "id": "g1", "arguments": {"path": "/etc/shadow"}},
        ]
    )
    loop = AgentLoop(tools={"guarded": guard_loop_ctx["tool"]}, model=model)
    try:
        guard_loop_ctx["result"] = asyncio.run(loop.run([]))
    except Exception as exc:  # noqa: BLE001
        guard_loop_ctx["exc"] = exc


@then("the guarded loop raises UserFixableError")
def _then_guarded_raises(guard_loop_ctx: dict[str, Any]) -> None:
    assert isinstance(guard_loop_ctx["exc"], UserFixableError)
