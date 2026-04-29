"""Tests for HookChain pre/post tool hooks."""

from __future__ import annotations

from typing import Any

import pytest

from pyarnes_core.errors import LLMRecoverableError
from pyarnes_harness.hooks import HookChain

# ── Helpers ────────────────────────────────────────────────────────────────


async def _identity_pre(tool: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
    return None


async def _double_x_pre(tool: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
    if "x" in arguments:
        return {**arguments, "x": arguments["x"] * 2}
    return None


async def _veto_pre(tool: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
    raise LLMRecoverableError(message="vetoed by pre-hook")


async def _append_post(tool: str, arguments: dict[str, Any], result: Any, is_error: bool) -> Any:
    if isinstance(result, str):
        return result + "_appended"
    return result


async def _error_override_post(tool: str, arguments: dict[str, Any], result: Any, is_error: bool) -> Any:
    if is_error:
        return "recovered"
    return result


# ── Pre-hook tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pre_hook_identity_returns_original_arguments() -> None:
    chain = HookChain(pre=[_identity_pre])
    result = await chain.run_pre("my_tool", {"a": 1})
    assert result == {"a": 1}


@pytest.mark.asyncio
async def test_pre_hook_modifies_arguments() -> None:
    chain = HookChain(pre=[_double_x_pre])
    result = await chain.run_pre("my_tool", {"x": 5})
    assert result == {"x": 10}


@pytest.mark.asyncio
async def test_pre_hook_veto_raises_llm_recoverable_error() -> None:
    chain = HookChain(pre=[_veto_pre])
    with pytest.raises(LLMRecoverableError):
        await chain.run_pre("my_tool", {})


@pytest.mark.asyncio
async def test_pre_hooks_chain_in_order() -> None:
    """Second hook receives the output of the first."""
    results: list[dict] = []

    async def record_pre(tool: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
        results.append(dict(arguments))
        return {**arguments, "count": arguments.get("count", 0) + 1}

    chain = HookChain(pre=[record_pre, record_pre])
    final = await chain.run_pre("t", {"count": 0})
    assert final == {"count": 2}
    assert results[0] == {"count": 0}
    assert results[1] == {"count": 1}


@pytest.mark.asyncio
async def test_empty_pre_chain_returns_original_arguments() -> None:
    chain = HookChain()
    args = {"key": "value"}
    result = await chain.run_pre("tool", args)
    assert result == args


# ── Post-hook tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_post_hook_modifies_result() -> None:
    chain = HookChain(post=[_append_post])
    result = await chain.run_post("tool", {}, "hello", is_error=False)
    assert result == "hello_appended"


@pytest.mark.asyncio
async def test_post_hook_receives_is_error_flag() -> None:
    chain = HookChain(post=[_error_override_post])
    result = await chain.run_post("tool", {}, "original_error", is_error=True)
    assert result == "recovered"


@pytest.mark.asyncio
async def test_post_hook_passes_through_when_no_error() -> None:
    chain = HookChain(post=[_error_override_post])
    result = await chain.run_post("tool", {}, "ok", is_error=False)
    assert result == "ok"


@pytest.mark.asyncio
async def test_empty_post_chain_returns_original_result() -> None:
    chain = HookChain()
    result = await chain.run_post("tool", {}, 42, is_error=False)
    assert result == 42


@pytest.mark.asyncio
async def test_post_hooks_chain_in_order() -> None:
    """Each post hook receives the previous hook's output."""

    async def add_a(tool: str, arguments: dict, result: Any, is_error: bool) -> Any:
        return result + "a"

    async def add_b(tool: str, arguments: dict, result: Any, is_error: bool) -> Any:
        return result + "b"

    chain = HookChain(post=[add_a, add_b])
    result = await chain.run_post("tool", {}, "", is_error=False)
    assert result == "ab"
