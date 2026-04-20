"""Shared fixtures for the Copier-template smoke tests.

``source_dir`` returns a non-VCS copy of the monorepo because Copier's
local-clone path fails under ``/tmp`` hardlink semantics. ``run_copy`` is
a thin wrapper that merges every test's ``data`` overrides onto a sane
default set, so test bodies stay focused on the behaviour they assert.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

copier = pytest.importorskip("copier")

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def source_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Non-VCS copy of the monorepo suitable for ``copier.run_copy``."""
    src = tmp_path_factory.mktemp("pyarnes_src")
    shutil.copytree(
        REPO_ROOT,
        src,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(
            ".git",
            ".venv",
            "node_modules",
            "__pycache__",
        ),
    )
    return src


@pytest.fixture
def run_copy(source_dir: Path):
    """Return a helper that renders the template into ``dest`` with ``data`` overrides."""

    def _run(dest: Path, /, **data: Any) -> Path:
        copier.run_copy(
            str(source_dir),
            str(dest),
            defaults=True,
            unsafe=True,
            data=data,
        )
        return dest

    return _run
