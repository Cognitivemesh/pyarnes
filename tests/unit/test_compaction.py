"""Tests for token-budget compaction pipeline."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from pyarnes_core.observability import estimate_tokens
from pyarnes_harness.compaction import (
    CompactionConfig,
    CompactionTransformer,
    _find_cut_index,
    compact,
)

# ── Helpers ────────────────────────────────────────────────────────────────


def _make_user(content: str) -> dict[str, Any]:
    return {"role": "user", "content": content}


def _make_assistant(content: str) -> dict[str, Any]:
    return {"role": "assistant", "content": content}


def _make_tool_call(content: str, tool_call_id: str = "t1") -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": content,
        "tool_calls": [{"id": tool_call_id, "type": "function", "function": {"name": "fn", "arguments": "{}"}}],
    }


def _make_tool_result(tool_call_id: str = "t1", content: str = "ok") -> dict[str, Any]:
    return {"role": "tool", "tool_call_id": tool_call_id, "content": content}


def _long_content(chars: int) -> str:
    return "x" * chars


# ── Unit: estimate_tokens ───────────────────────────────────────────────────
#
# The shared estimator now lives in ``pyarnes_core.observability.tokens`` and
# uses ``len(json.dumps(obj)) // 4`` so JSON-serialisable objects (messages,
# tool result dicts, audit graph fragments) all get the same approximation.


def test_estimate_tokens_empty_list() -> None:
    # `[]` → "[]" → 2 chars → 0 tokens.
    assert estimate_tokens([]) == 0


def test_estimate_tokens_grows_with_content() -> None:
    # A 100-char user message dumps to roughly 130 chars (envelope + content),
    # which is ~32 tokens with the //4 rule. Keep the assertion loose so we are
    # robust to JSON whitespace/encoding tweaks.
    msgs = [_make_user("a" * 100)]
    assert estimate_tokens(msgs) >= 25
    # A 1000-char message must be markedly larger than the 100-char one.
    big = [_make_user("a" * 1000)]
    assert estimate_tokens(big) > estimate_tokens(msgs) * 5


def test_estimate_tokens_includes_non_string_content() -> None:
    # Unlike the old harness-private helper, the JSON-based estimator counts
    # the envelope of every message — including `None` / dict tool results.
    msgs = [{"role": "tool", "tool_call_id": "x", "content": None}]
    assert estimate_tokens(msgs) > 0


# ── Unit: _find_cut_index ──────────────────────────────────────────────────


def test_find_cut_index_no_cut_needed() -> None:
    """Short history: cut index is 0 (no compaction needed)."""
    msgs = [_make_user("hi"), _make_assistant("hello")]
    idx = _find_cut_index(msgs, keep_tokens=10_000)
    assert idx == 0


def test_find_cut_index_cuts_at_turn_boundary() -> None:
    """Cut moves work older once the per-message budget is breached."""
    msgs = [
        _make_user(_long_content(4_000)),  # heavy — old
        _make_assistant(_long_content(4_000)),  # heavy — old
        _make_user(_long_content(4_000)),  # heavy — keep
        _make_assistant(_long_content(4_000)),  # heavy — keep
    ]
    # Each ~4 000-char message is ~1 000 tokens; keep_tokens=2_500 keeps the
    # last two and cuts after idx 1.
    idx = _find_cut_index(msgs, keep_tokens=2_500)
    assert idx == 2


def test_find_cut_index_never_splits_tool_pair() -> None:
    """Cut must not separate a tool_call from its immediately following tool_result."""
    msgs = [
        _make_user(_long_content(4_000)),
        _make_assistant(_long_content(4_000)),
        _make_tool_call(_long_content(4_000)),  # idx 2 — pair member
        _make_tool_result(content=_long_content(4_000)),  # idx 3 — pair member
    ]
    # keep_tokens just above one message worth → natural cut would land on
    # the orphan tool result at idx 3; the helper backs it up to idx 2 so
    # the call/result pair stays intact.
    idx = _find_cut_index(msgs, keep_tokens=1_500)
    assert idx == 2


# ── Integration: compact ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_compact_short_history_returns_original() -> None:
    """Short message history does not trigger compaction."""
    model = AsyncMock()
    model.next_action = AsyncMock()

    msgs = [_make_user("hi"), _make_assistant("hello")]
    config = CompactionConfig(keep_recent_tokens=10_000)
    result = await compact(msgs, model, config)
    assert result == msgs
    model.next_action.assert_not_called()


@pytest.mark.asyncio
async def test_compact_long_history_summarizes_old_segment() -> None:
    """Long history: old segment is replaced by a summary message."""

    async def fake_next_action(messages: list[dict]) -> dict:
        return {"role": "assistant", "content": "[summary of earlier conversation]"}

    model = AsyncMock()
    model.next_action = AsyncMock(side_effect=fake_next_action)

    old = [_make_user(_long_content(4000)), _make_assistant(_long_content(4000))]
    recent = [_make_user(_long_content(100)), _make_assistant(_long_content(100))]
    msgs = old + recent

    config = CompactionConfig(keep_recent_tokens=100)  # keep only ~100 tokens
    result = await compact(msgs, model, config)

    assert len(result) < len(msgs)
    # The summary message should appear first
    assert result[0]["role"] == "user"
    # Recent messages must be preserved intact at the end
    assert result[-2:] == recent


@pytest.mark.asyncio
async def test_compact_savings_ratio_skips_when_insufficient() -> None:
    """If compaction saves less than min_savings_ratio, return original."""
    model = AsyncMock()
    # Summary is almost as long as original — no benefit
    summary_text = _long_content(3900)  # close to original 4000 chars

    async def fake_next_action(messages: list[dict]) -> dict:
        return {"role": "assistant", "content": summary_text}

    model.next_action = AsyncMock(side_effect=fake_next_action)

    old = [_make_user(_long_content(2000)), _make_assistant(_long_content(2000))]
    recent = [_make_user("keep me")]
    msgs = old + recent

    config = CompactionConfig(keep_recent_tokens=50, min_savings_ratio=0.10)
    result = await compact(msgs, model, config)
    # Should return original because savings ratio is too low
    assert result == msgs


@pytest.mark.asyncio
async def test_compact_never_splits_tool_pair() -> None:
    """Cut point must never land between a tool_call and its tool result."""
    model = AsyncMock()

    async def fake_next_action(messages: list[dict]) -> dict:
        return {"role": "assistant", "content": "[summary]"}

    model.next_action = AsyncMock(side_effect=fake_next_action)

    msgs = [
        _make_user(_long_content(4000)),
        _make_assistant(_long_content(4000)),
        _make_tool_call(_long_content(100)),
        _make_tool_result(content=_long_content(100)),
        _make_user("final"),
    ]

    config = CompactionConfig(keep_recent_tokens=400)
    result = await compact(msgs, model, config)

    # Find tool_call index in result — there must be a paired tool result immediately after
    tool_call_indices = [i for i, m in enumerate(result) if m.get("tool_calls")]
    for tc_idx in tool_call_indices:
        assert tc_idx + 1 < len(result), "tool_call at end with no paired result"
        assert result[tc_idx + 1]["role"] == "tool", "tool_call not paired with tool result"


# ── CompactionTransformer ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_compaction_transformer_delegates_to_compact() -> None:
    """CompactionTransformer.__call__ applies compact() and returns result."""
    model = AsyncMock()

    async def fake_next_action(messages: list[dict]) -> dict:
        return {"role": "assistant", "content": "[summary]"}

    model.next_action = AsyncMock(side_effect=fake_next_action)

    old = [_make_user(_long_content(4000)), _make_assistant(_long_content(4000))]
    recent = [_make_user("keep")]
    msgs = old + recent

    transformer = CompactionTransformer(model=model, config=CompactionConfig(keep_recent_tokens=50))
    result = await transformer(msgs)

    assert len(result) < len(msgs)
    assert result[-1] == recent[-1]
