"""BDD step definitions for harness error-handling scenarios."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from pytest_bdd import given, parsers, scenario, then, when

from pyarnes_core.errors import (
    LLMRecoverableError,
    TransientError,
    UnexpectedError,
    UserFixableError,
)
from pyarnes_core.types import ModelClient, ToolHandler
from pyarnes_harness.loop import AgentLoop, LoopConfig

# ── Scenarios ──────────────────────────────────────────────────────────────


@scenario("../harness.feature", "Transient error triggers retry")
def test_transient_retry() -> None:
    """Transient error triggers retry."""


@scenario("../harness.feature", "LLM-recoverable error feeds back to the model")
def test_llm_recoverable() -> None:
    """LLM-recoverable error feeds back to the model."""


@scenario("../harness.feature", "User-fixable error interrupts the loop")
def test_user_fixable() -> None:
    """User-fixable error interrupts the loop."""


@scenario("../harness.feature", "Unexpected error bubbles up")
def test_unexpected() -> None:
    """Unexpected error bubbles up."""


# ── Helpers ────────────────────────────────────────────────────────────────


@dataclass
class FakeModel(ModelClient):
    """Scripted model responses."""

    actions: list[dict[str, Any]]
    _idx: int = 0

    async def next_action(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        action = self.actions[self._idx]
        self._idx += 1
        return action


@dataclass
class FailTool(ToolHandler):
    """Tool that always raises the given exception."""

    exc: BaseException

    async def execute(self, arguments: dict[str, Any]) -> Any:
        raise self.exc


# ── Steps ──────────────────────────────────────────────────────────────────


@given("a tool that raises a transient error", target_fixture="harness_ctx")
def _given_transient() -> dict[str, Any]:
    tool = FailTool(exc=TransientError(message="timeout"))
    model = FakeModel(
        actions=[
            {"type": "tool_call", "tool": "t", "id": "c1", "arguments": {}},
            {"type": "final_answer", "content": "done"},
        ]
    )
    loop = AgentLoop(
        tools={"t": tool},
        model=model,
        config=LoopConfig(max_retries=1, retry_base_delay=0.01),
    )
    return {"loop": loop, "result": None, "exc": None}


@given("a tool that raises an LLM-recoverable error", target_fixture="harness_ctx")
def _given_llm_recoverable() -> dict[str, Any]:
    tool = FailTool(exc=LLMRecoverableError(message="bad schema"))
    model = FakeModel(
        actions=[
            {"type": "tool_call", "tool": "t", "id": "c2", "arguments": {}},
            {"type": "final_answer", "content": "done"},
        ]
    )
    loop = AgentLoop(tools={"t": tool}, model=model)
    return {"loop": loop, "result": None, "exc": None}


@given("a tool that raises a user-fixable error", target_fixture="harness_ctx")
def _given_user_fixable() -> dict[str, Any]:
    tool = FailTool(exc=UserFixableError(message="need auth"))
    model = FakeModel(actions=[{"type": "tool_call", "tool": "t", "id": "c3", "arguments": {}}])
    loop = AgentLoop(tools={"t": tool}, model=model)
    return {"loop": loop, "result": None, "exc": None}


@given("a tool that raises an unexpected exception", target_fixture="harness_ctx")
def _given_unexpected() -> dict[str, Any]:
    tool = FailTool(exc=RuntimeError("boom"))
    model = FakeModel(actions=[{"type": "tool_call", "tool": "t", "id": "c4", "arguments": {}}])
    loop = AgentLoop(tools={"t": tool}, model=model)
    return {"loop": loop, "result": None, "exc": None}


@when("the harness executes the tool")
def _when_execute(harness_ctx: dict[str, Any]) -> None:
    loop: AgentLoop = harness_ctx["loop"]
    try:
        harness_ctx["result"] = asyncio.run(loop.run([]))
    except Exception as e:
        harness_ctx["exc"] = e


@then("the tool is retried up to the configured limit")
def _then_retried(harness_ctx: dict[str, Any]) -> None:
    # If retried and exhausted, we get a tool message with "Transient failure"
    result = harness_ctx["result"]
    assert result is not None


@then(parsers.parse("the error is returned as a tool message"))
def _then_tool_message(harness_ctx: dict[str, Any]) -> None:
    result = harness_ctx["result"]
    tool_msgs = [m for m in result if m.get("role") == "tool"]
    assert any(m.get("is_error") for m in tool_msgs)


@then("the error is returned as a tool message with is_error true")
def _then_is_error(harness_ctx: dict[str, Any]) -> None:
    result = harness_ctx["result"]
    tool_msgs = [m for m in result if m.get("role") == "tool"]
    assert any(m.get("is_error") is True for m in tool_msgs)


@then("the loop raises a UserFixableError")
def _then_user_fixable_raised(harness_ctx: dict[str, Any]) -> None:
    assert isinstance(harness_ctx["exc"], UserFixableError)


@then("the loop raises an UnexpectedError")
def _then_unexpected_raised(harness_ctx: dict[str, Any]) -> None:
    assert isinstance(harness_ctx["exc"], UnexpectedError)
