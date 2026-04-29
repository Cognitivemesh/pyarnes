"""Tests for layered message transformation pipeline."""

from __future__ import annotations

from typing import Any

import pytest

from pyarnes_harness.transform import TransformChain

# ── Helpers ────────────────────────────────────────────────────────────────


async def _append_marker(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [*messages, {"role": "system", "content": "marked"}]


async def _prepend_system(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"role": "system", "content": "prefix"}, *messages]


async def _uppercase_content(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**m, "content": m["content"].upper()} if isinstance(m.get("content"), str) else m for m in messages]


# ── TransformChain tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_chain_is_identity() -> None:
    chain = TransformChain()
    msgs = [{"role": "user", "content": "hello"}]
    result = await chain.apply(msgs)
    assert result == msgs


@pytest.mark.asyncio
async def test_single_stage_applied() -> None:
    chain = TransformChain(stages=[_append_marker])
    msgs = [{"role": "user", "content": "hello"}]
    result = await chain.apply(msgs)
    assert len(result) == 2
    assert result[-1]["content"] == "marked"


@pytest.mark.asyncio
async def test_stages_applied_in_order() -> None:
    """prepend_system runs first, then append_marker — order matters."""
    chain = TransformChain(stages=[_prepend_system, _append_marker])
    msgs = [{"role": "user", "content": "hi"}]
    result = await chain.apply(msgs)
    assert result[0]["content"] == "prefix"
    assert result[-1]["content"] == "marked"
    assert result[1]["content"] == "hi"


@pytest.mark.asyncio
async def test_stage_mutation_threaded_through() -> None:
    """Second stage sees the output of the first."""
    chain = TransformChain(stages=[_uppercase_content, _append_marker])
    msgs = [{"role": "user", "content": "hello"}]
    result = await chain.apply(msgs)
    assert result[0]["content"] == "HELLO"
    assert result[-1]["content"] == "marked"


@pytest.mark.asyncio
async def test_original_messages_not_mutated() -> None:
    chain = TransformChain(stages=[_append_marker])
    msgs = [{"role": "user", "content": "x"}]
    original = list(msgs)
    await chain.apply(msgs)
    assert msgs == original


@pytest.mark.asyncio
async def test_callable_transformer_accepted() -> None:
    """Any async callable matching the transformer signature works."""

    async def noop(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return messages

    chain = TransformChain(stages=[noop])
    msgs = [{"role": "user", "content": "test"}]
    result = await chain.apply(msgs)
    assert result == msgs
