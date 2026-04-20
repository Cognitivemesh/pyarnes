"""Path-parts containment atom — parts-prefix comparison, not string prefix.

Addresses bug A2: ``str.startswith`` treats siblings with a shared name
prefix as contained (``/workspace_evil``.startswith(``/workspace``) is
``True``). Comparing ``Path.parts`` tuples eliminates the confusion.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from pyarnes_core.safety.atoms.path_canon import canonicalize

__all__ = [
    "is_within_roots",
]


def is_within_roots(path: str | Path, roots: Iterable[str | Path]) -> bool:
    """Return True when *path* is equal to or nested under any *roots* entry.

    Both *path* and each root are canonicalized, then compared by
    :attr:`Path.parts` tuples. This correctly rejects sibling directories
    that merely share a name prefix.

    Args:
        path: Candidate path.
        roots: Iterable of allowed root paths.

    Returns:
        ``True`` when *path* is within some root; ``False`` otherwise.
        Returns ``False`` when *roots* is empty (no roots → nothing allowed).
    """
    resolved = canonicalize(path)
    resolved_parts = resolved.parts
    for root in roots:
        root_parts = canonicalize(root).parts
        if resolved_parts[: len(root_parts)] == root_parts:
            return True
    return False
