"""Layered message transformation pipeline.

Decouples internal message state from what gets sent to the LLM. Each stage
is an async callable that receives and returns a message list. Stages are
applied in declaration order; compaction and context-injection hooks plug in
here without touching ``AgentLoop`` internals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

__all__ = [
    "MessageTransformer",
    "TransformChain",
]


class MessageTransformer(Protocol):
    """Async callable that maps a message list to a (transformed) message list."""

    async def __call__(  # noqa: D102
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]: ...


@dataclass
class TransformChain:
    """Ordered pipeline of message transformers.

    Attributes:
        stages: Transformers applied left-to-right. Each stage receives the
            output of the previous one.
    """

    stages: list[MessageTransformer] = field(default_factory=list)

    async def apply(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Apply all stages in order, threading mutations through.

        Args:
            messages: Input message list (not mutated).

        Returns:
            Transformed message list.
        """
        current = messages
        for stage in self.stages:
            current = await stage(current)
        return current
