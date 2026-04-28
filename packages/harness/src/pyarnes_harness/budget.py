"""IterationBudget — shared, thread-safe loop-iteration counter.

A single ``IterationBudget`` instance can be shared across a parent agent
and any sub-agents spawned during its run. This makes the total work cap
apply globally, not per-loop-instance, which prevents runaway tool chains.

Refund mechanism
----------------
Programmatic tool calls (e.g. code execution that internally calls other
tools) can ``refund`` iterations they did not "consume" from the user's
perspective, preventing the budget from being unfairly drained.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

__all__ = ["IterationBudget"]


@dataclass
class IterationBudget:
    """Shared async-safe iteration counter.

    Attributes:
        total: Maximum number of iterations allowed across all consumers.
    """

    total: int = 90
    _remaining: int = field(init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    def __post_init__(self) -> None:  # noqa: D105
        if self.total < 1:
            msg = "IterationBudget.total must be >= 1"
            raise ValueError(msg)
        self._remaining = self.total

    @property
    def remaining(self) -> int:
        """Current remaining iterations (snapshot, not synchronized)."""
        return self._remaining

    async def consume(self, n: int = 1) -> bool:
        """Decrement budget by *n*.

        Returns:
            ``True`` if the budget had enough remaining and was decremented.
            ``False`` if the budget is exhausted (caller should stop the loop).
        """
        async with self._lock:
            if self._remaining < n:
                return False
            self._remaining -= n
            return True

    async def refund(self, n: int = 1) -> None:
        """Return *n* iterations to the budget (capped at ``total``)."""
        async with self._lock:
            self._remaining = min(self._remaining + n, self.total)
