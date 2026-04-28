"""Tests for AgentRuntime — the single entry-point harness wiring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from pyarnes_core.errors import UserFixableError
from pyarnes_core.lifecycle import Phase
from pyarnes_core.types import ModelClient, ToolHandler
from pyarnes_harness.runtime import AgentRuntime

# ── Helpers ────────────────────────────────────────────────────────────────


@dataclass
class FakeModel(ModelClient):
    """Model that returns a scripted sequence of actions."""

    actions: list[dict[str, Any]]
    _index: int = 0

    async def next_action(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        action = self.actions[self._index]
        self._index += 1
        return action


@dataclass
class EchoTool(ToolHandler):
    """Tool that echoes its arguments."""

    async def execute(self, arguments: dict[str, Any]) -> Any:
        return arguments.get("text", "echo")


@dataclass
class FailingTool(ToolHandler):
    """Tool that raises a given exception."""

    exc: BaseException

    async def execute(self, arguments: dict[str, Any]) -> Any:
        raise self.exc


def _simple_runtime(**kwargs: Any) -> AgentRuntime:
    """Build a minimal AgentRuntime with a single echo tool and one-shot model."""
    model = FakeModel(actions=[{"type": "final_answer", "content": "done"}])
    return AgentRuntime(tools={"echo": EchoTool()}, model=model, **kwargs)


# ── Tests ──────────────────────────────────────────────────────────────────


class TestAgentRuntimeHappyPath:
    """Successful run transitions lifecycle to COMPLETED."""

    @pytest.mark.asyncio()
    async def test_lifecycle_completed_on_success(self) -> None:
        runtime = _simple_runtime()
        await runtime.run([])
        assert runtime.lifecycle is not None
        assert runtime.lifecycle.phase == Phase.COMPLETED

    @pytest.mark.asyncio()
    async def test_run_returns_messages(self) -> None:
        runtime = _simple_runtime()
        result = await runtime.run([])
        assert isinstance(result, list)
        assert any(m.get("type") == "final_answer" for m in result)


class TestAgentRuntimeFailurePath:
    """Exceptions from the loop transition lifecycle to FAILED and re-raise."""

    @pytest.mark.asyncio()
    async def test_lifecycle_failed_on_exception(self) -> None:
        model = FakeModel(
            actions=[
                {"type": "tool_call", "tool": "bad", "id": "f1", "arguments": {}},
            ]
        )
        runtime = AgentRuntime(
            tools={"bad": FailingTool(exc=UserFixableError(message="auth needed"))},
            model=model,
        )
        with pytest.raises(UserFixableError):
            await runtime.run([])
        assert runtime.lifecycle is not None
        assert runtime.lifecycle.phase == Phase.FAILED

    @pytest.mark.asyncio()
    async def test_exception_is_reraised(self) -> None:
        model = FakeModel(
            actions=[
                {"type": "tool_call", "tool": "bad", "id": "f2", "arguments": {}},
            ]
        )
        exc = UserFixableError(message="must reraise")
        runtime = AgentRuntime(
            tools={"bad": FailingTool(exc=exc)},
            model=model,
        )
        with pytest.raises(UserFixableError, match="must reraise"):
            await runtime.run([])


class TestAgentRuntimeSessionId:
    """session_id is auto-generated when None; preserved when provided."""

    @pytest.mark.asyncio()
    async def test_session_id_auto_generated(self) -> None:
        runtime = _simple_runtime()
        assert runtime.session_id is None
        await runtime.run([])
        assert runtime.session_id is not None
        assert len(runtime.session_id) == 12

    @pytest.mark.asyncio()
    async def test_session_id_preserved_when_provided(self) -> None:
        runtime = _simple_runtime(session_id="mycustomid12")
        await runtime.run([])
        assert runtime.session_id == "mycustomid12"

    @pytest.mark.asyncio()
    async def test_session_id_is_hex(self) -> None:
        runtime = _simple_runtime()
        await runtime.run([])
        assert runtime.session_id is not None
        # All characters must be valid hex digits.
        int(runtime.session_id, 16)
