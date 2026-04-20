"""Path canonicalization atoms — collapse ``..`` and resolve symlinks.

Addresses bug A1: ``PurePosixPath`` is a lexical type and does not
collapse ``..``. Any downstream check that relies on string-prefix
matching will accept ``/workspace/../etc/passwd`` as in-root.

Usage::

    from pyarnes_core.safety.atoms import canonicalize, has_traversal

    if has_traversal(user_input):
        raise UserFixableError(...)
    resolved = canonicalize(user_input)
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

__all__ = [
    "canonicalize",
    "has_traversal",
]


def has_traversal(value: str | Path) -> bool:
    r"""Return True when *value* contains a ``..`` segment or a NUL byte.

    Defense in depth: even after canonicalization, we reject inputs with
    traversal segments so that symlink-induced edge cases cannot sneak
    through. NUL bytes are rejected because they terminate C-strings on
    many kernels and can mask subsequent path components from filesystem
    APIs.

    Args:
        value: Candidate path as ``str`` or ``Path``.

    Returns:
        ``True`` if *value* has a ``..`` part or contains ``\x00``.
    """
    text = str(value)
    if "\x00" in text:
        return True
    return ".." in PurePosixPath(text).parts


def canonicalize(value: str | Path) -> Path:
    """Return the fully resolved absolute form of *value*.

    Uses :meth:`Path.resolve` with ``strict=False`` so non-existent paths
    still get a normalized form (important for write-target validation
    before a file is created). Symlinks are followed.

    Args:
        value: Candidate path as ``str`` or ``Path``.

    Returns:
        A canonical absolute :class:`Path`.

    Raises:
        ValueError: If *value* contains a NUL byte.
    """
    text = str(value)
    if "\x00" in text:
        msg = "Path contains NUL byte"
        raise ValueError(msg)
    return Path(text).resolve(strict=False)
