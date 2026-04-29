"""Tests for the agent loop."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from pyarnes_core import Lifecycle, Phase
from pyarnes_core.error_registry import ErrorHandlerRegistry
from pyarnes_core.errors import (
    HarnessError,
    LLMRecoverableError,
    TransientError,
    UnexpectedError,
    UserFixableError,
)
from pyarnes_core.types import ModelClient, ToolHandler
from pyarnes_harness.loop import AgentLoop, LoopConfig, ToolMessage

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


class TestRetryDelayPrecision:
    """Exact retry delay values emitted by the loop under monkeypatched sleep."""

    @pytest.mark.asyncio()
    async def test_config_base_delay_wins_when_greater_than_error_default(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Config base delay of 1.5 beats the TransientError default of 1.0."""
        sleeps: list[float] = []

        async def fake_sleep(delay: float) -> None:
            sleeps.append(delay)

        monkeypatch.setattr("asyncio.sleep", fake_sleep)

        # TransientError default retry_delay_seconds=1.0; config=1.5 → merged=1.5.
        tool = FailingTool(exc=TransientError(message="blip"))
        model = FakeModel(
            actions=[
                {"type": "tool_call", "tool": "t", "id": "d1", "arguments": {}},
                {"type": "final_answer", "content": "done"},
            ]
        )
        loop = AgentLoop(
            tools={"t": tool},
            model=model,
            config=LoopConfig(max_retries=1, retry_base_delay=1.5),
        )
        await loop.run([])
        # attempt=0 → 1.5 * 2^0 = 1.5
        assert sleeps and sleeps[0] == pytest.approx(1.5)

    @pytest.mark.asyncio()
    async def test_second_retry_delay_is_doubled(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        sleeps: list[float] = []

        async def fake_sleep(delay: float) -> None:
            sleeps.append(delay)

        monkeypatch.setattr("asyncio.sleep", fake_sleep)

        calls = {"n": 0}

        class AlwaysTransient(ToolHandler):
            async def execute(self, arguments: dict[str, Any]) -> Any:
                del arguments
                calls["n"] += 1
                # Explicit delay=1.5 beats the default 1.0 and the config 1.0.
                raise TransientError(message="always fails", retry_delay_seconds=1.5)

        model = FakeModel(
            actions=[
                {"type": "tool_call", "tool": "t", "id": "d2", "arguments": {}},
                {"type": "final_answer", "content": "done"},
            ]
        )
        loop = AgentLoop(
            tools={"t": AlwaysTransient()},
            model=model,
            config=LoopConfig(max_retries=2, retry_base_delay=1.0),
        )
        await loop.run([])
        # merged base = max(1.0, 1.5) = 1.5; attempt=0 → 1.5; attempt=1 → 3.0
        assert len(sleeps) == 2
        assert sleeps[0] == pytest.approx(1.5)
        assert sleeps[1] == pytest.approx(3.0)

    @pytest.mark.asyncio()
    async def test_loop_does_not_execute_iteration_n_plus_one(self) -> None:
        """The loop must stop at exactly max_iterations, not max_iterations+1."""
        max_iter = 4
        call_count = {"n": 0}

        class CountingEcho(ToolHandler):
            async def execute(self, arguments: dict[str, Any]) -> Any:
                del arguments
                call_count["n"] += 1
                return "echo"

        actions = [{"type": "tool_call", "tool": "echo", "id": f"e{i}", "arguments": {}} for i in range(max_iter + 5)]
        model = FakeModel(actions=actions)
        loop = AgentLoop(
            tools={"echo": CountingEcho()},
            model=model,
            config=LoopConfig(max_iterations=max_iter),
        )
        await loop.run([])
        assert call_count["n"] == max_iter


class TestConcurrentLoopIsolation:
    """Two AgentLoop instances running concurrently must not share state."""

    @pytest.mark.asyncio()
    async def test_two_loops_separate_tool_registries(self) -> None:
        results_a: list[Any] = []
        results_b: list[Any] = []

        class RecordingTool(ToolHandler):
            def __init__(self, store: list[Any]) -> None:
                self._store = store

            async def execute(self, arguments: dict[str, Any]) -> Any:
                self._store.append(arguments.get("tag"))
                return arguments.get("tag", "?")

        tool_a = RecordingTool(results_a)
        tool_b = RecordingTool(results_b)

        model_a = FakeModel(
            actions=[
                {"type": "tool_call", "tool": "tool", "id": "a1", "arguments": {"tag": "A"}},
                {"type": "final_answer", "content": "done"},
            ]
        )
        model_b = FakeModel(
            actions=[
                {"type": "tool_call", "tool": "tool", "id": "b1", "arguments": {"tag": "B"}},
                {"type": "final_answer", "content": "done"},
            ]
        )

        loop_a = AgentLoop(tools={"tool": tool_a}, model=model_a)
        loop_b = AgentLoop(tools={"tool": tool_b}, model=model_b)

        await asyncio.gather(loop_a.run([]), loop_b.run([]))

        # Each tool saw only its own tags.
        assert results_a == ["A"]
        assert results_b == ["B"]

    @pytest.mark.asyncio()
    async def test_lifecycle_instances_do_not_share_history(self) -> None:
        lc_a = Lifecycle(phase=Phase.INIT)
        lc_b = Lifecycle(phase=Phase.INIT)

        lc_a.transition(Phase.RUNNING)
        lc_a.transition(Phase.PAUSED)

        # lc_b must not see lc_a's transitions.
        assert lc_b.phase == Phase.INIT
        assert len(lc_b.history) == 0


class TestReflectionInterval:
    """LoopConfig.reflection_interval fires at the right iterations."""

    def _make_counting_model(
        self,
        *,
        normal_responses: list[dict[str, Any]],
    ) -> tuple[Any, list[int]]:
        """Return a model and a mutable list that records which calls were reflection probes."""
        reflection_calls: list[int] = []
        call_counter: list[int] = [0]
        normal_iter: list[int] = [0]

        class CountingModel:
            async def next_action(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
                call_counter[0] += 1
                # Reflection probes end with the sentinel phrase
                last = messages[-1] if messages else {}
                if "REFLECTION CHECKPOINT" in last.get("content", ""):
                    reflection_calls.append(call_counter[0])
                    return {"role": "assistant", "content": "reflecting"}
                idx = normal_iter[0]
                normal_iter[0] += 1
                return normal_responses[idx]

        return CountingModel(), reflection_calls

    @pytest.mark.asyncio()
    async def test_reflection_disabled_when_zero(self) -> None:
        responses = [
            {"type": "tool_call", "tool": "echo", "id": "r1", "arguments": {}},
            {"type": "tool_call", "tool": "echo", "id": "r2", "arguments": {}},
            {"type": "final_answer", "content": "done"},
        ]
        model, reflections = self._make_counting_model(normal_responses=responses)
        loop = AgentLoop(
            tools={"echo": EchoTool()},
            model=model,
            config=LoopConfig(reflection_interval=0),
        )
        await loop.run([])
        assert reflections == []

    @pytest.mark.asyncio()
    async def test_reflection_fires_at_interval(self) -> None:
        # interval=2, max_iterations=5 → reflection fires at iterations 2 and 4 only
        responses = [
            {"type": "tool_call", "tool": "echo", "id": "r1", "arguments": {}},
            {"type": "tool_call", "tool": "echo", "id": "r2", "arguments": {}},
            {"type": "tool_call", "tool": "echo", "id": "r3", "arguments": {}},
            {"type": "tool_call", "tool": "echo", "id": "r4", "arguments": {}},
            {"type": "final_answer", "content": "done"},
        ]
        model, reflections = self._make_counting_model(normal_responses=responses)
        loop = AgentLoop(
            tools={"echo": EchoTool()},
            model=model,
            config=LoopConfig(reflection_interval=2, max_iterations=5),
        )
        await loop.run([])
        assert len(reflections) == 2

    @pytest.mark.asyncio()
    async def test_reflection_skips_when_interval_exceeds_max(self) -> None:
        responses = [
            {"type": "tool_call", "tool": "echo", "id": "r1", "arguments": {}},
            {"type": "final_answer", "content": "done"},
        ]
        model, reflections = self._make_counting_model(normal_responses=responses)
        loop = AgentLoop(
            tools={"echo": EchoTool()},
            model=model,
            config=LoopConfig(reflection_interval=10, max_iterations=5),
        )
        await loop.run([])
        assert reflections == []


# ── ErrorHandlerRegistry integration ──────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _CustomHarnessError(HarnessError):
    """Custom HarnessError subtype used in ErrorHandlerRegistry integration tests."""


class TestErrorRegistryIntegration:
    """AgentLoop consults ErrorHandlerRegistry in the HarnessError catch-all branch."""

    @pytest.mark.asyncio()
    async def test_registered_handler_short_circuits_unexpected_error(self) -> None:
        """A handler that returns a ToolMessage prevents UnexpectedError from raising."""
        replacement = ToolMessage(tool_call_id="c1", content="recovered", is_error=True)

        async def handler(exc: HarnessError) -> ToolMessage:
            return replacement

        registry = ErrorHandlerRegistry()
        registry.register(_CustomHarnessError, handler)

        tool = FailingTool(exc=_CustomHarnessError(message="custom"))
        model = FakeModel(
            actions=[
                {"type": "tool_call", "tool": "t", "id": "c1", "arguments": {}},
                {"type": "final_answer", "content": "done"},
            ]
        )
        loop = AgentLoop(tools={"t": tool}, model=model, error_registry=registry)
        result = await loop.run([])
        tool_msgs = [m for m in result if m.get("role") == "tool"]
        assert tool_msgs[0]["content"] == "recovered"
        assert tool_msgs[0]["is_error"] is True

    @pytest.mark.asyncio()
    async def test_handler_returning_none_falls_through_to_unexpected_error(self) -> None:
        """When the handler returns None, UnexpectedError is still raised."""

        async def none_handler(exc: HarnessError) -> None:
            return None

        registry = ErrorHandlerRegistry()
        registry.register(_CustomHarnessError, none_handler)

        tool = FailingTool(exc=_CustomHarnessError(message="still unexpected"))
        model = FakeModel(
            actions=[
                {"type": "tool_call", "tool": "t", "id": "c2", "arguments": {}},
            ]
        )
        loop = AgentLoop(tools={"t": tool}, model=model, error_registry=registry)
        with pytest.raises(UnexpectedError):
            await loop.run([])

    @pytest.mark.asyncio()
    async def test_unregistered_harness_error_raises_unexpected(self) -> None:
        """HarnessError subtypes with no registered handler still raise UnexpectedError."""
        registry = ErrorHandlerRegistry()  # empty — no handlers

        tool = FailingTool(exc=_CustomHarnessError(message="unhandled"))
        model = FakeModel(
            actions=[
                {"type": "tool_call", "tool": "t", "id": "c3", "arguments": {}},
            ]
        )
        loop = AgentLoop(tools={"t": tool}, model=model, error_registry=registry)
        with pytest.raises(UnexpectedError):
            await loop.run([])

    @pytest.mark.asyncio()
    async def test_handler_returning_non_tool_message_raises_unexpected(self) -> None:
        """A handler that returns a non-ToolMessage raises UnexpectedError with a clear message."""
        registry = ErrorHandlerRegistry()

        async def bad_handler(exc: HarnessError) -> object:
            return "this is not a ToolMessage"

        registry.register(_CustomHarnessError, bad_handler)  # type: ignore[arg-type]

        tool = FailingTool(exc=_CustomHarnessError(message="trigger"))
        model = FakeModel(actions=[{"type": "tool_call", "tool": "t", "id": "c4", "arguments": {}}])
        loop = AgentLoop(tools={"t": tool}, model=model, error_registry=registry)
        with pytest.raises(UnexpectedError, match=r"str.*expected ToolMessage"):
            await loop.run([])
