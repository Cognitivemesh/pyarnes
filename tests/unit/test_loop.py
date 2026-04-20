"""Tests for the agent loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from pyarnes_core.errors import (
    LLMRecoverableError,
    TransientError,
    UnexpectedError,
    UserFixableError,
)
from pyarnes_core.types import ModelClient, ToolHandler
from pyarnes_harness.loop import AgentLoop, LoopConfig

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
    """Tool that raises a given exception type."""

    exc: BaseException

    async def execute(self, arguments: dict[str, Any]) -> Any:
        raise self.exc


# ── Tests ──────────────────────────────────────────────────────────────────


class TestLoopConfig:
    """LoopConfig validates its inputs."""

    def test_default_values(self) -> None:
        cfg = LoopConfig()
        assert cfg.max_iterations == 50
        assert cfg.max_retries == 2

    def test_invalid_iterations(self) -> None:
        with pytest.raises(ValueError, match="max_iterations"):
            LoopConfig(max_iterations=0)

    def test_invalid_retries(self) -> None:
        with pytest.raises(ValueError, match="max_retries"):
            LoopConfig(max_retries=-1)


class TestAgentLoop:
    """Core loop behaviour."""

    @pytest.fixture()
    def echo_tools(self) -> dict[str, EchoTool]:
        return {"echo": EchoTool()}

    @pytest.mark.asyncio()
    async def test_single_tool_call_then_answer(self, echo_tools: dict[str, EchoTool]) -> None:
        model = FakeModel(
            actions=[
                {"type": "tool_call", "tool": "echo", "id": "c1", "arguments": {"text": "hi"}},
                {"type": "final_answer", "content": "done"},
            ]
        )
        loop = AgentLoop(tools=echo_tools, model=model)
        result = await loop.run([])
        # Should contain: tool_call, tool_result, final_answer
        assert any(m.get("type") == "final_answer" for m in result)

    @pytest.mark.asyncio()
    async def test_unknown_tool_returns_error(self) -> None:
        model = FakeModel(
            actions=[
                {"type": "tool_call", "tool": "nonexistent", "id": "c2", "arguments": {}},
                {"type": "final_answer", "content": "ok"},
            ]
        )
        loop = AgentLoop(tools={}, model=model)
        result = await loop.run([])
        tool_msg = [m for m in result if m.get("role") == "tool"]
        assert tool_msg[0]["is_error"] is True

    @pytest.mark.asyncio()
    async def test_transient_error_retries(self) -> None:
        tool = FailingTool(exc=TransientError(message="timeout"))
        model = FakeModel(
            actions=[
                {"type": "tool_call", "tool": "flaky", "id": "c3", "arguments": {}},
                {"type": "final_answer", "content": "done"},
            ]
        )
        loop = AgentLoop(
            tools={"flaky": tool},
            model=model,
            config=LoopConfig(max_retries=1, retry_base_delay=0.01),
        )
        result = await loop.run([])
        tool_msg = [m for m in result if m.get("role") == "tool"]
        assert tool_msg[0]["is_error"] is True
        assert "Transient failure" in tool_msg[0]["content"]

    @pytest.mark.asyncio()
    async def test_llm_recoverable_feeds_back(self) -> None:
        tool = FailingTool(exc=LLMRecoverableError(message="bad schema"))
        model = FakeModel(
            actions=[
                {"type": "tool_call", "tool": "strict", "id": "c4", "arguments": {}},
                {"type": "final_answer", "content": "adjusted"},
            ]
        )
        loop = AgentLoop(tools={"strict": tool}, model=model)
        result = await loop.run([])
        tool_msg = [m for m in result if m.get("role") == "tool"]
        assert tool_msg[0]["is_error"] is True
        assert "model can retry" in tool_msg[0]["content"]

    @pytest.mark.asyncio()
    async def test_user_fixable_raises(self) -> None:
        tool = FailingTool(exc=UserFixableError(message="auth needed"))
        model = FakeModel(
            actions=[
                {"type": "tool_call", "tool": "auth", "id": "c5", "arguments": {}},
            ]
        )
        loop = AgentLoop(tools={"auth": tool}, model=model)
        with pytest.raises(UserFixableError, match="auth needed"):
            await loop.run([])

    @pytest.mark.asyncio()
    async def test_unexpected_error_raises(self) -> None:
        tool = FailingTool(exc=RuntimeError("boom"))
        model = FakeModel(
            actions=[
                {"type": "tool_call", "tool": "bad", "id": "c6", "arguments": {}},
            ]
        )
        loop = AgentLoop(tools={"bad": tool}, model=model)
        with pytest.raises(UnexpectedError, match="boom"):
            await loop.run([])

    @pytest.mark.asyncio()
    async def test_transient_error_override_raises_retry_cap(self) -> None:
        """A TransientError's max_retries must override the LoopConfig floor."""
        calls = {"n": 0}

        class FlakyThenOk(ToolHandler):
            async def execute(self, arguments: dict[str, Any]) -> Any:
                del arguments
                calls["n"] += 1
                if calls["n"] <= 3:
                    raise TransientError(message="blip", max_retries=4)
                return "eventually"

        model = FakeModel(
            actions=[
                {"type": "tool_call", "tool": "flaky", "id": "b5", "arguments": {}},
                {"type": "final_answer", "content": "done"},
            ]
        )
        loop = AgentLoop(
            tools={"flaky": FlakyThenOk()},
            model=model,
            config=LoopConfig(max_retries=2, retry_base_delay=0.001),
        )
        result = await loop.run([])
        tool_msg = [m for m in result if m.get("role") == "tool"]
        assert tool_msg[0]["is_error"] is False
        assert "eventually" in tool_msg[0]["content"]
        assert calls["n"] == 4

    @pytest.mark.asyncio()
    async def test_transient_error_override_raises_delay(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A TransientError's retry_delay_seconds must outrank LoopConfig."""
        sleeps: list[float] = []

        async def fake_sleep(delay: float) -> None:
            sleeps.append(delay)

        monkeypatch.setattr("asyncio.sleep", fake_sleep)

        tool = FailingTool(exc=TransientError(message="slow", retry_delay_seconds=2.0))
        model = FakeModel(
            actions=[
                {"type": "tool_call", "tool": "t", "id": "b6", "arguments": {}},
                {"type": "final_answer", "content": "done"},
            ]
        )
        loop = AgentLoop(
            tools={"t": tool},
            model=model,
            config=LoopConfig(max_retries=1, retry_base_delay=0.5),
        )
        await loop.run([])
        assert sleeps and sleeps[0] == 2.0

    @pytest.mark.asyncio()
    async def test_unknown_action_type_is_recoverable(self) -> None:
        """Malformed actions must not dispatch to tool_name=''."""
        model = FakeModel(
            actions=[
                {"type": "thinking"},
                {"type": "final_answer", "content": "ok"},
            ]
        )
        loop = AgentLoop(tools={}, model=model)
        result = await loop.run([])
        tool_results = [m for m in result if m.get("role") == "tool"]
        assert tool_results
        assert tool_results[0]["is_error"] is True
        assert "Unrecognized action type" in tool_results[0]["content"]

    @pytest.mark.asyncio()
    async def test_max_iterations_limit(self) -> None:
        # Model never returns final_answer → loop should stop after max_iterations.
        max_iter = 3
        num_tool_calls = max_iter + 1  # more than max_iterations to ensure the loop stops
        actions = [
            {"type": "tool_call", "tool": "echo", "id": f"c{i}", "arguments": {"text": "go"}}
            for i in range(num_tool_calls)
        ]
        model = FakeModel(actions=actions)
        loop = AgentLoop(
            tools={"echo": EchoTool()},
            model=model,
            config=LoopConfig(max_iterations=max_iter),
        )
        result = await loop.run([])
        # Should have exactly max_iter iterations worth of tool results
        tool_results = [m for m in result if m.get("role") == "tool"]
        assert len(tool_results) == max_iter
