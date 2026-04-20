"""Atom: recursive argument walking.

Guardrails that only inspect top-level scalar values miss list
arguments (``{"paths": [...]}``), nested dicts
(``{"opts": {"path": ...}}``), and multi-field shapes
(``{"source": ..., "dest": ...}``). These helpers walk any nested
``dict``/``list``/``tuple`` structure bounded by *max_depth* to
prevent pathological inputs from exhausting the stack.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

__all__ = [
    "walk_strings",
    "walk_values_for_keys",
]


def walk_strings(value: Any, *, max_depth: int = 10) -> Iterator[str]:
    """Yield every ``str`` reachable through nested dict/list/tuple.

    Non-string leaves (``int``, ``bytes``, ``None``, etc.) are ignored
    silently. Recursion stops at *max_depth* to bound worst-case cost.

    Args:
        value: Arbitrary value to walk.
        max_depth: Maximum recursion depth (inclusive). A value of 0
            yields nothing when *value* is a container.

    Yields:
        Each ``str`` leaf, in traversal order.
    """
    if max_depth < 0:
        return
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from walk_strings(item, max_depth=max_depth - 1)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            yield from walk_strings(item, max_depth=max_depth - 1)


def walk_values_for_keys(
    arguments: dict[str, Any],
    keys: Iterable[str],
    *,
    max_depth: int = 10,
) -> Iterator[Any]:
    """Yield every value found under any *keys* entry at any nesting depth.

    Traverses *arguments* (and nested dicts/lists/tuples) collecting the
    raw value of each matching key. Callers can then pipe the results
    through :func:`walk_strings` to get the concrete strings.

    Args:
        arguments: The top-level arguments dict.
        keys: Key names to match at every depth.
        max_depth: Maximum recursion depth (inclusive).

    Yields:
        The raw value associated with each matching key.
    """
    target = frozenset(keys)
    yield from _walk_values(arguments, target, max_depth)


def _walk_values(
    value: Any,
    target: frozenset[str],
    depth: int,
) -> Iterator[Any]:
    if depth < 0:
        return
    if isinstance(value, dict):
        for k, v in value.items():
            if k in target:
                yield v
            yield from _walk_values(v, target, depth - 1)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk_values(item, target, depth - 1)
