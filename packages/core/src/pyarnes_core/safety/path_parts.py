"""Atom: path-parts containment — parts-prefix comparison, not string prefix.

``str.startswith`` treats siblings with a shared name prefix as
contained (``/workspace_evil``.startswith(``/workspace``) is ``True``).
Comparing ``Path.parts`` tuples eliminates the confusion.
"""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

from funcy import some

from pyarnes_core.safety.path_canon import canonicalize

__all__ = [
    "is_within_roots",
]


@lru_cache(maxsize=256)
def _canonical_parts(root: str) -> tuple[str, ...]:
    return canonicalize(root).parts


def is_within_roots(path: str | Path, roots: Iterable[str | Path]) -> bool:
    """Return True when *path* is equal to or nested under any *roots* entry.

    Both *path* and each root are canonicalized, then compared by
    :attr:`Path.parts` tuples. This correctly rejects sibling directories
    that merely share a name prefix.

    Root canonicalization is cached per string, so repeat calls with the
    same guardrail configuration pay the ``Path.resolve`` cost once.

    Args:
        path: Candidate path.
        roots: Iterable of allowed root paths.

    Returns:
        ``True`` when *path* is within some root; ``False`` otherwise.
        Returns ``False`` when *roots* is empty (no roots → nothing allowed).
    """
    resolved_parts = canonicalize(path).parts
    return bool(
        some(
            lambda rp: resolved_parts[: len(rp)] == rp,
            (_canonical_parts(str(root)) for root in roots),
        )
    )
