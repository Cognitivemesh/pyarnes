"""Tests for ContextCompressor auto-trigger wrapper."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from pyarnes_harness.compaction import CompactionConfig
from pyarnes_harness.compressor import ContextCompressor

# ── Helpers ────────────────────────────────────────────────────────────────


def _make_user(content: str) -> dict[str, Any]:
    return {"role": "user", "content": content}


def _make_assistant(content: str) -> dict[str, Any]:
    return {"role": "assistant", "content": content}


# ── ContextCompressor tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_below_threshold_returns_messages_unchanged() -> None:
    """When token usage is below capacity_threshold, messages pass through."""
    model = MagicMock()
    model.next_action = AsyncMock()

    msgs = [_make_user("hi"), _make_assistant("hello")]
    # 4 chars per message → ~2 tokens each → ~4 tokens total
    # context_window=1000, threshold=0.75 → trigger at 750 tokens
    compressor = ContextCompressor(model=model, context_window=1000, capacity_threshold=0.75)
    result = await compressor(msgs)

    assert result == msgs
    model.next_action.assert_not_called()


@pytest.mark.asyncio
async def test_above_threshold_triggers_compaction() -> None:
    """When token usage >= capacity * threshold, compaction is applied."""

    async def fake_next_action(messages: list[dict]) -> dict:
        return {"role": "assistant", "content": "[summary]"}

    model = MagicMock()
    model.next_action = AsyncMock(side_effect=fake_next_action)

    # Each message: 1000 chars → 250 tokens. Two messages = 500 tokens.
    # context_window=500, threshold=0.75 → trigger at 375 tokens. 500 > 375 → compact.
    msgs = [_make_user("a" * 1000), _make_assistant("b" * 1000)]
    compressor = ContextCompressor(
        model=model,
        context_window=500,
        capacity_threshold=0.75,
        config=CompactionConfig(keep_recent_tokens=10),
    )
    result = await compressor(msgs)

    # Compaction was attempted — result differs from input
    assert result != msgs or model.next_action.called


@pytest.mark.asyncio
async def test_at_exact_threshold_triggers_compaction() -> None:
    """Trigger is inclusive: usage == threshold * context_window fires compaction."""

    async def fake_next_action(messages: list[dict]) -> dict:
        return {"role": "assistant", "content": "[s]"}

    model = MagicMock()
    model.next_action = AsyncMock(side_effect=fake_next_action)

    # 400 chars → 100 tokens. context_window=100, threshold=1.0 → trigger at 100.
    msgs = [_make_user("a" * 400)]
    compressor = ContextCompressor(
        model=model,
        context_window=100,
        capacity_threshold=1.0,
        config=CompactionConfig(keep_recent_tokens=10),
    )
    result = await compressor(msgs)

    assert model.next_action.called or result != msgs


@pytest.mark.asyncio
async def test_custom_config_passed_to_compact() -> None:
    """CompactionConfig is forwarded to compact() — keep_recent_tokens respected."""

    async def fake_next_action(messages: list[dict]) -> dict:
        return {"role": "assistant", "content": "[summary]"}

    model = MagicMock()
    model.next_action = AsyncMock(side_effect=fake_next_action)

    old = [_make_user("a" * 4000), _make_assistant("b" * 4000)]  # 2000 tok
    recent = [_make_user("keep me")]  # ~2 tok
    msgs = old + recent

    compressor = ContextCompressor(
        model=model,
        context_window=100,
        capacity_threshold=0.01,  # always trigger
        config=CompactionConfig(keep_recent_tokens=50),
    )
    result = await compressor(msgs)

    # Recent message must appear at the end
    assert result[-1]["content"] == "keep me"
    # Result should be shorter than original
    assert len(result) < len(msgs)
