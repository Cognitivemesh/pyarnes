"""Token-budget compaction with split-turn safety.

Backward-scans the message history to find a safe cut point, summarizes the
older segment via an LLM call, and replaces it with a single user-role
summary message.  The recent segment is always preserved verbatim.

Cut-point invariant
-------------------
A cut must never fall between a tool_call assistant turn and its immediately
following ``"tool"`` result.  If the natural cut lands on a ``"tool"`` message
the implementation moves the boundary one step earlier so both pair members
stay in the kept segment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pyarnes_core.types import ModelClient

__all__ = [
    "CompactionConfig",
    "CompactionTransformer",
    "compact",
]

_SUMMARY_PREFIX = "[Earlier conversation summary]"


@dataclass(frozen=True)
class CompactionConfig:
    """Tunables for the compaction algorithm.

    Attributes:
        keep_recent_tokens: Token budget for the intact recent segment.
        reserve_tokens: Headroom reserved for response generation (unused by
            the cut-finder; available for callers that compute context limits).
        min_savings_ratio: Skip compaction when the summary saves less than
            this fraction of the total token count.
        tokens_per_char: Rough char-to-token ratio used by ``_estimate_tokens``.
    """

    keep_recent_tokens: int = 20_000
    reserve_tokens: int = 16_000
    min_savings_ratio: float = 0.10
    tokens_per_char: float = 0.25


@dataclass
class CompactionTransformer:
    """MessageTransformer that wraps ``compact()`` for use in a TransformChain.

    Attributes:
        model: LLM client used to generate summaries.
        config: Compaction tunables.
    """

    model: ModelClient
    config: CompactionConfig = field(default_factory=CompactionConfig)

    async def __call__(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Apply compaction to *messages*, returning the (possibly shorter) history."""
        return await compact(messages, self.model, self.config)


# ── Internal helpers ────────────────────────────────────────────────────────


def _estimate_tokens(messages: list[dict[str, Any]], tokens_per_char: float = 0.25) -> int:
    """Estimate total token count from message content lengths."""
    total = 0
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str):
            total += int(len(content) * tokens_per_char)
    return total


def _find_cut_index(
    messages: list[dict[str, Any]],
    keep_tokens: int,
    tokens_per_char: float = 0.25,
) -> int:
    """Backward scan returning the index of the first message to keep.

    Returns 0 when all messages fit within *keep_tokens* (no compaction needed).
    Moves the cut one step earlier when it would land on a ``"tool"`` result,
    preserving the tool_call/tool_result pair in the kept segment.

    Args:
        messages: Full message history.
        keep_tokens: Maximum tokens to keep intact.
        tokens_per_char: Char-to-token ratio for estimation.

    Returns:
        Index of the first message in the kept (recent) segment.
    """
    if not messages:
        return 0

    accumulated = 0
    for i in range(len(messages) - 1, -1, -1):
        msg_tokens = _estimate_tokens([messages[i]], tokens_per_char)
        if accumulated + msg_tokens > keep_tokens:
            cut = i + 1
            # Maintain pair integrity: if the kept segment starts with an orphan
            # tool result, move the boundary one step earlier.
            if cut < len(messages) and messages[cut].get("role") == "tool":
                cut -= 1
                if cut <= 0:
                    return 0
            return cut
        accumulated += msg_tokens

    return 0  # all messages fit within keep_tokens


async def _summarize_segment(segment: list[dict[str, Any]], model: ModelClient) -> dict[str, Any]:
    """Ask *model* to summarize *segment* and return a single user-role message."""
    lines = []
    for msg in segment:
        role = msg.get("role", "").upper()
        content = msg.get("content")
        if isinstance(content, str) and content:
            lines.append(f"{role}: {content}")

    prompt_text = (
        "Summarize the following conversation segment concisely so it can serve "
        "as context for continuing the conversation:\n\n" + "\n".join(lines)
    )
    action = await model.next_action([{"role": "user", "content": prompt_text}])
    summary_text = action.get("content", "")
    return {"role": "user", "content": f"{_SUMMARY_PREFIX}\n{summary_text}"}


# ── Public API ──────────────────────────────────────────────────────────────


async def compact(
    messages: list[dict[str, Any]],
    model: ModelClient,
    config: CompactionConfig,
) -> list[dict[str, Any]]:
    """Compact *messages* by summarizing the oldest segment.

    Returns the original list unchanged when:
    - No cut point is found (all messages fit within *keep_recent_tokens*).
    - The summary saves less than *min_savings_ratio* of total tokens.

    Args:
        messages: Full conversation history.
        model: LLM client used to generate the summary.
        config: Compaction tunables.

    Returns:
        Compacted message list, or the original if compaction is not beneficial.
    """
    cut = _find_cut_index(messages, config.keep_recent_tokens, config.tokens_per_char)
    if cut == 0:
        return messages

    old_segment = messages[:cut]
    recent_segment = messages[cut:]

    summary = await _summarize_segment(old_segment, model)
    compacted = [summary, *recent_segment]

    original_tokens = _estimate_tokens(messages, config.tokens_per_char)
    compacted_tokens = _estimate_tokens(compacted, config.tokens_per_char)
    if original_tokens == 0:
        return messages
    savings_ratio = (original_tokens - compacted_tokens) / original_tokens
    if savings_ratio < config.min_savings_ratio:
        return messages

    return compacted
