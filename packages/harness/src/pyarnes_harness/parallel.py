"""Parallel tool batch detection and execution.

When an LLM returns multiple tool calls in one response, this module decides
whether they can run concurrently (path-independent, no interactive tools) or
must run serially, then dispatches accordingly.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

__all__ = [
    "SERIAL_TOOLS",
    "can_parallelize",
    "execute_batch",
]

# Tools that require human-in-the-loop or sequential state — never parallelize.
SERIAL_TOOLS: frozenset[str] = frozenset({"clarify", "ask_user", "input"})


def can_parallelize(calls: list[dict[str, Any]]) -> bool:
    """Return True if all calls are safe to run concurrently.

    Two conditions must both hold:
    1. No call uses a name in ``SERIAL_TOOLS``.
    2. No two calls share the same ``path`` argument (write-path independence).
    """
    if not calls:
        return True

    for call in calls:
        if call.get("tool") in SERIAL_TOOLS:
            return False

    paths: list[str] = []
    for call in calls:
        args = call.get("arguments") or {}
        p = args.get("path")
        if p is not None:
            if p in paths:
                return False
            paths.append(p)

    return True


async def execute_batch(
    calls: list[dict[str, Any]],
    handler_fn: Callable[[str, str, dict[str, Any]], Coroutine[Any, Any, Any]],
) -> list[Any]:
    """Dispatch a batch of tool calls, parallelizing when safe.

    Args:
        calls: Tool call dicts, each with ``tool``, ``id``, and ``arguments``.
        handler_fn: Async callable ``(name, call_id, arguments) -> result``.

    Returns:
        Results in the same order as *calls*.
    """
    if can_parallelize(calls):
        tasks = [
            handler_fn(c["tool"], c.get("id", ""), c.get("arguments") or {})
            for c in calls
        ]
        return list(await asyncio.gather(*tasks))

    results: list[Any] = []
    for call in calls:
        result = await handler_fn(call["tool"], call.get("id", ""), call.get("arguments") or {})
        results.append(result)
    return results
