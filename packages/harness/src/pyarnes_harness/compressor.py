"""ContextCompressor — capacity-fraction auto-trigger wrapper around compaction.

Plugs into a ``TransformChain`` as a ``MessageTransformer``.  Instead of
requiring callers to pick a fixed token count, it fires compaction once the
estimated usage reaches *capacity_threshold* of the model's context window.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pyarnes_core.observability import estimate_tokens
from pyarnes_core.types import ModelClient
from pyarnes_harness.compaction import CompactionConfig, compact

__all__ = ["ContextCompressor"]


@dataclass
class ContextCompressor:
    """Message transformer that compacts when token usage crosses a capacity fraction.

    Attributes:
        model: LLM client used to generate summaries.
        context_window: Maximum token capacity of the model (e.g. 128_000).
        capacity_threshold: Fraction of *context_window* at which compaction fires.
            Default is 0.75 (trigger at 75 % full).
        config: Compaction tunables forwarded to ``compact()``.
    """

    model: ModelClient
    context_window: int
    capacity_threshold: float = 0.75
    config: CompactionConfig = field(default_factory=CompactionConfig)

    async def __call__(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return compacted messages if above threshold, otherwise pass through."""
        used = estimate_tokens(messages)
        if used < self.context_window * self.capacity_threshold:
            return messages
        return await compact(messages, self.model, self.config)
