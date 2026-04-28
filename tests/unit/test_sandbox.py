"""Tests for SandboxHook, RestrictedPythonSandbox, SeccompSandbox, and AgentLoop integration."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock

import pytest

from pyarnes_core.sandbox import RestrictedPythonSandbox, SandboxHook, SeccompSandbox


# ── Protocol conformance ──────────────────────────────────────────────────────


class TestSandboxHookProtocol:
    def test_concrete_class_satisfies_protocol(self) -> None:
        @dataclass
        class MySandbox:
            async def enter(self) -> None:
                pass

            async def exit(self, exc: BaseException | None) -> None:
                pass

        assert isinstance(MySandbox(), SandboxHook)

    def test_missing_exit_fails_protocol_check(self) -> None:
        @dataclass
        class BadSandbox:
            async def enter(self) -> None:
                pass

        assert not isinstance(BadSandbox(), SandboxHook)

    def test_missing_enter_fails_protocol_check(self) -> None:
        @dataclass
        class BadSandbox:
            async def exit(self, exc: BaseException | None) -> None:
                pass

        assert not isinstance(BadSandbox(), SandboxHook)


# ── RestrictedPythonSandbox ───────────────────────────────────────────────────


class TestRestrictedPythonSandbox:
    def test_raises_import_error_when_package_absent(self, monkeypatch) -> None:
        import builtins
        import importlib

        original_import = builtins.__import__

        def _block(name, *args, **kwargs):
            if name == "RestrictedPython":
                raise ImportError("mocked absent")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _block)
        with pytest.raises(ImportError, match="restrictedpython"):
            RestrictedPythonSandbox()

    def test_policy_default(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "pyarnes_core.sandbox.RestrictedPythonSandbox.__post_init__", lambda self: None
        )
        sb = RestrictedPythonSandbox()
        assert sb.policy == "default"

    def test_enter_and_exit_are_no_ops(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "pyarnes_core.sandbox.RestrictedPythonSandbox.__post_init__", lambda self: None
        )
        import asyncio

        sb = RestrictedPythonSandbox()
        asyncio.run(sb.enter())
        asyncio.run(sb.exit(None))


# ── SeccompSandbox ────────────────────────────────────────────────────────────


class TestSeccompSandbox:
    def test_no_op_on_non_linux(self, monkeypatch) -> None:
        monkeypatch.setattr(sys, "platform", "darwin")
        sb = SeccompSandbox()
        assert sb.allowed_syscalls == frozenset()

    def test_raises_import_error_on_linux_when_seccomp_absent(self, monkeypatch) -> None:
        monkeypatch.setattr(sys, "platform", "linux")
        import builtins

        original_import = builtins.__import__

        def _block(name, *args, **kwargs):
            if name == "seccomp":
                raise ImportError("mocked absent")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _block)
        with pytest.raises(ImportError, match="seccomp"):
            SeccompSandbox()

    def test_allowed_syscalls_stored(self, monkeypatch) -> None:
        monkeypatch.setattr(sys, "platform", "darwin")
        syscalls = frozenset({"read", "write"})
        sb = SeccompSandbox(allowed_syscalls=syscalls)
        assert sb.allowed_syscalls == syscalls

    def test_enter_noop_on_non_linux(self, monkeypatch) -> None:
        monkeypatch.setattr(sys, "platform", "darwin")
        import asyncio

        sb = SeccompSandbox()
        asyncio.run(sb.enter())

    def test_exit_noop(self, monkeypatch) -> None:
        monkeypatch.setattr(sys, "platform", "darwin")
        import asyncio

        sb = SeccompSandbox()
        asyncio.run(sb.exit(None))
        asyncio.run(sb.exit(ValueError("oops")))


# ── AgentLoop sandbox integration ─────────────────────────────────────────────


@pytest.mark.asyncio
class TestAgentLoopSandbox:
    """Sandbox enter/exit called around tool execution."""

    def _make_loop(self, tool_fn, sandbox=None):
        from pyarnes_core.dispatch.ports import ModelClient, ToolHandler
        from pyarnes_harness.loop import AgentLoop

        class _Tool(ToolHandler):
            async def execute(self, arguments: dict[str, Any]) -> Any:
                return await tool_fn(arguments)

        class _Model(ModelClient):
            _called = False

            async def next_action(self, messages):
                if self._called:
                    return {"type": "final_answer", "content": "done"}
                self._called = True
                return {"type": "tool_call", "tool": "mytool", "id": "tc1", "arguments": {}}

        return AgentLoop(
            tools={"mytool": _Tool()},
            model=_Model(),
            sandbox=sandbox,
        )

    async def test_enter_and_exit_called_on_success(self) -> None:
        calls: list[str] = []

        @dataclass
        class _Spy:
            async def enter(self) -> None:
                calls.append("enter")

            async def exit(self, exc: BaseException | None) -> None:
                calls.append(f"exit:{exc}")

        loop = self._make_loop(lambda _: _async_const("ok"), sandbox=_Spy())
        await loop.run([{"role": "user", "content": "go"}])
        assert "enter" in calls
        assert "exit:None" in calls

    async def test_exit_called_with_exception(self) -> None:
        from pyarnes_core.errors import LLMRecoverableError

        captured_exc: list[BaseException | None] = []

        @dataclass
        class _Spy:
            async def enter(self) -> None:
                pass

            async def exit(self, exc: BaseException | None) -> None:
                captured_exc.append(exc)

        async def _raise(_):
            raise LLMRecoverableError(message="boom")

        loop = self._make_loop(_raise, sandbox=_Spy())
        await loop.run([{"role": "user", "content": "go"}])
        assert len(captured_exc) == 1
        assert isinstance(captured_exc[0], LLMRecoverableError)

    async def test_no_sandbox_works_normally(self) -> None:
        loop = self._make_loop(lambda _: _async_const("result"), sandbox=None)
        msgs = await loop.run([{"role": "user", "content": "go"}])
        assert any(m.get("role") == "tool" for m in msgs)


async def _async_const(value):
    return value
