"""Molecule: sandbox containment.

Composes :func:`has_traversal`, :func:`canonicalize`, and
:func:`is_within_roots` into a single assertion used by
``PathGuardrail``.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from pyarnes_core.errors import UserFixableError
from pyarnes_core.safety.path_canon import canonicalize, has_traversal
from pyarnes_core.safety.path_parts import is_within_roots

__all__ = [
    "assert_within_roots",
]


def assert_within_roots(
    path: str | Path,
    roots: Iterable[str | Path],
) -> Path:
    """Canonicalize *path* and confirm it is under one of *roots*.

    Rejects traversal segments and NUL bytes up-front, then collapses
    the path and compares ``Path.parts`` tuples against each root
    (parts comparison — not string-prefix matching).

    Args:
        path: Candidate path from a tool argument.
        roots: Allowed root directories (canonicalized per-call).

    Returns:
        The canonical :class:`Path` on success.

    Raises:
        UserFixableError: When *path* contains traversal, a NUL byte, or
            falls outside every configured root.
    """
    roots_tuple = tuple(roots)
    if has_traversal(path):
        raise UserFixableError(
            message=f"Path '{path}' contains a traversal segment",
            prompt_hint=f"Provide an absolute path under {roots_tuple}",
        )
    resolved = canonicalize(path)
    if not is_within_roots(resolved, roots_tuple):
        raise UserFixableError(
            message=f"Path '{resolved}' is outside allowed roots {roots_tuple}",
            prompt_hint=f"Allow access to '{resolved}'?",
        )
    return resolved
