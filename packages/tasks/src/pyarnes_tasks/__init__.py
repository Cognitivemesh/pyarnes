"""Cross-platform task runner — replaces Make.

Usage::

    uv run tasks lint
    uv run tasks format
    uv run tasks test
    uv run tasks check       # lint + typecheck + test
    uv run tasks watch       # TDD watch mode
    uv run tasks docs        # generate docstrings
    uv run tasks security    # bandit scan
    uv run tasks md-lint     # markdown lint
    uv run tasks yaml-lint   # yaml lint

Configuration lives in ``pyproject.toml`` under ``[tool.pyarnes-tasks]``::

    [tool.pyarnes-tasks]
    sources = ["src"]       # ruff / ty / bandit / radon / vulture targets
    tests = ["tests"]        # pytest test roots (silently skipped if missing)
    packages = []            # extra roots for monorepos
"""

from __future__ import annotations

from pyarnes_tasks.cli import main

__all__ = ["main"]
