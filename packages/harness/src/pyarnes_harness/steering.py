"""Steering queue — inject mid-execution user notes into the agent loop.

Callers push steering notes from a concurrent task; the loop drains them at
the start of each iteration and prepends them to the message history as
``user``-role messages. This is softer than raising ``UserFixableError``
because it does not interrupt the current tool call.

Thread-safety: all state is guarded by an ``asyncio.Lock`` so concurrent
``push`` and ``drain`` calls from different coroutines do not race.
"""

from __future__ import annotations

import asyncio
from typing import Any

__all__ = ["SteeringQueue"]


class SteeringQueue:
    """Async-safe queue of steering notes for the agent loop.

    Usage::

        steering = SteeringQueue()
        # From a concurrent task:
        await steering.push("Please prioritise memory efficiency.")
        # The loop calls this at the top of each iteration:
        notes = await steering.drain()
        messages.extend(notes)
    """

    def __init__(self) -> None:
        """Initialise an empty queue."""
        self._notes: list[str] = []
        self._lock: asyncio.Lock = asyncio.Lock()

    async def push(self, content: str) -> None:
        """Enqueue a steering note.

        Args:
            content: The note text to inject as a user message.
        """
        async with self._lock:
            self._notes.append(content)

    async def drain(self) -> list[dict[str, Any]]:
        """Return and clear all pending steering notes as user-role dicts.

        Returns:
            List of ``{"role": "user", "content": ...}`` message dicts,
            one per queued note, in push order. Empty when no notes pending.
        """
        async with self._lock:
            notes, self._notes = self._notes, []
        return [{"role": "user", "content": note} for note in notes]
