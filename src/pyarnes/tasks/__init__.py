"""Cross-platform task runner — replaces Make.

Usage::

    uv run tasks lint
    uv run tasks format
    uv run tasks test
    uv run tasks check       # lint + types + test
    uv run tasks watch       # TDD watch mode
    uv run tasks docs        # generate docstrings
    uv run tasks security    # bandit scan
    uv run tasks md-lint     # markdown lint
    uv run tasks yaml-lint   # yaml lint
"""

from __future__ import annotations

from pyarnes.tasks.cli import main

__all__ = ["main"]
