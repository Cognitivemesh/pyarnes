"""Atom: version_of — read a package's version from installed metadata.

A hard-coded ``__version__ = "0.1.0"`` literal drifts the moment any
``pyproject.toml`` is bumped. This helper reads the version from
``importlib.metadata`` so every ``__init__.py`` becomes a single line.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

__all__ = [
    "version_of",
]


def version_of(distribution_name: str) -> str:
    """Return the installed version of *distribution_name*.

    Args:
        distribution_name: The PyPI distribution name (e.g. ``pyarnes-core``).

    Returns:
        The version string from the installed metadata, or ``"0+unknown"``
        when the distribution is not installed (editable-install edge cases
        and bare source-tree runs).
    """
    try:
        return version(distribution_name)
    except PackageNotFoundError:
        return "0+unknown"
