"""Resolve declarative target placeholders to real paths.

A `ShellPlugin` declares ``targets = ("sources", "tests")`` (or literal
paths). This module expands those placeholders against the
``[tool.pyarnes-tasks]`` table in the project's ``pyproject.toml``,
filtering out paths that don't exist so a freshly-scaffolded project
without a ``tests/`` directory still gets a working ``uv run tasks check``.

Reused from the original ``cli.py`` helpers; centralised here so plugin
classes can call them without depending on the CLI module.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

__all__ = ["load_config", "resolve_targets"]

DEFAULT_SOURCES = ["src"]
DEFAULT_TESTS = ["tests"]


def _find_pyproject(start: Path) -> Path | None:
    for candidate in [start, *start.parents]:
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file():
            return pyproject
    return None


def load_config(root: Path) -> tuple[list[str], list[str]]:
    """Return ``(sources, tests)`` from ``[tool.pyarnes-tasks]``."""
    pyproject = _find_pyproject(root)
    if pyproject is None:
        return DEFAULT_SOURCES, DEFAULT_TESTS
    with pyproject.open("rb") as fh:
        data = tomllib.load(fh)
    tool = data.get("tool", {}).get("pyarnes-tasks", {})
    sources = list(tool.get("sources", DEFAULT_SOURCES))
    tests = list(tool.get("tests", DEFAULT_TESTS))
    return sources, tests


def resolve_targets(targets: tuple[str, ...], root: Path) -> list[str]:
    """Expand placeholders against ``root``; drop paths that don't exist.

    ``"sources"`` and ``"tests"`` are special placeholders. Anything else
    is treated as a literal path relative to ``root``.
    """
    if not targets:
        return []
    sources, tests = load_config(root)
    expanded: list[str] = []
    for t in targets:
        if t == "sources":
            expanded.extend(sources)
        elif t == "tests":
            expanded.extend(tests)
        else:
            expanded.append(t)
    return [p for p in expanded if (root / p).exists()]
