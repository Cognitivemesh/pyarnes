"""Copier template smoke tests — one per ``adopter_shape``.

These tests protect the Spec 02 contract: ``uvx copier copy`` against a
pinned ref must produce a working adopter project for every shape. They
use the ``copier`` Python API against a non-VCS copy of the monorepo to
avoid git's ``--filter=blob:none`` hardlink quirks under ``/tmp``.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

copier = pytest.importorskip("copier")


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def source_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Return a non-VCS copy of the monorepo copier reads from.

    Copier clones git repos before rendering; ``/tmp`` hardlink semantics
    break that clone on some file systems. A plain copy with ``.git``
    stripped is enough for structural validation.
    """
    src = tmp_path_factory.mktemp("pyarnes_src")
    shutil.copytree(REPO_ROOT, src, dirs_exist_ok=True, ignore=shutil.ignore_patterns(
        ".git", ".venv", "node_modules", "__pycache__",
    ))
    return src


@pytest.mark.parametrize(
    "shape",
    ["blank", "pii-redaction", "s3-sweep", "rtm-toggl-agile"],
)
def test_scaffold_generates(
    shape: str,
    source_dir: Path,
    tmp_path: Path,
) -> None:
    """Every adopter shape renders a minimum viable file tree."""
    dest = tmp_path / f"scaffold-{shape}"
    copier.run_copy(
        str(source_dir),
        str(dest),
        defaults=True,
        unsafe=True,
        data={
            "project_name": f"scaffold-{shape}",
            "project_description": f"scaffold smoke for {shape}",
            "adopter_shape": shape,
        },
    )

    module_dir = dest / "src" / f"scaffold_{shape.replace('-', '_')}"
    assert (dest / "pyproject.toml").is_file()
    assert (dest / "CLAUDE.md").is_file()
    assert (module_dir / "pipeline.py").is_file()
    assert (module_dir / "cli.py").is_file()
    assert (module_dir / "guardrails.py").is_file()
    assert (module_dir / "tools" / "__init__.py").is_file()

    pyproject = (dest / "pyproject.toml").read_text()
    assert "pyarnes-core" in pyproject
    assert "[project.scripts]" in pyproject
    assert f"scaffold_{shape.replace('-', '_')}.cli:app" in pyproject


def test_shape_specific_deps(source_dir: Path, tmp_path: Path) -> None:
    """Shape-specific runtime deps land in the generated pyproject.toml."""
    dest = tmp_path / "scaffold-deps-pii"
    copier.run_copy(
        str(source_dir),
        str(dest),
        defaults=True,
        unsafe=True,
        data={
            "project_name": "scaffold-deps-pii",
            "project_description": "pii deps",
            "adopter_shape": "pii-redaction",
        },
    )
    pyproject = (dest / "pyproject.toml").read_text()
    assert "presidio-analyzer" in pyproject
    assert "kreuzberg" in pyproject


def test_blank_has_no_shape_specific_deps(source_dir: Path, tmp_path: Path) -> None:
    """Blank shape keeps the dependency list minimal."""
    dest = tmp_path / "scaffold-deps-blank"
    copier.run_copy(
        str(source_dir),
        str(dest),
        defaults=True,
        unsafe=True,
        data={
            "project_name": "scaffold-deps-blank",
            "project_description": "blank deps",
            "adopter_shape": "blank",
        },
    )
    pyproject = (dest / "pyproject.toml").read_text()
    assert "presidio-analyzer" not in pyproject
    assert "boto3" not in pyproject
    assert "httpx" not in pyproject


def test_dev_hooks_ship_only_when_enabled(source_dir: Path, tmp_path: Path) -> None:
    """``.claude/hooks/`` and ``tests/bench/`` appear iff ``enable_dev_hooks`` is true."""
    dest_off = tmp_path / "no-hooks"
    copier.run_copy(
        str(source_dir),
        str(dest_off),
        defaults=True,
        unsafe=True,
        data={
            "project_name": "no-hooks",
            "project_description": "hooks off",
            "adopter_shape": "blank",
            "enable_dev_hooks": False,
        },
    )
    assert not (dest_off / ".claude" / "hooks" / "pyarnes_pre_tool.py").exists()
    assert not (dest_off / ".claude" / "settings.json").exists()
    assert not (dest_off / "tests" / "bench").exists()

    dest_on = tmp_path / "with-hooks"
    copier.run_copy(
        str(source_dir),
        str(dest_on),
        defaults=True,
        unsafe=True,
        data={
            "project_name": "with-hooks",
            "project_description": "hooks on",
            "adopter_shape": "rtm-toggl-agile",
            "enable_dev_hooks": True,
        },
    )
    assert (dest_on / ".claude" / "hooks" / "pyarnes_pre_tool.py").is_file()
    assert (dest_on / ".claude" / "hooks" / "pyarnes_post_tool.py").is_file()
    assert (dest_on / ".claude" / "settings.json").is_file()
    assert (dest_on / "tests" / "bench" / "test_agent_quality.py").is_file()

    settings = (dest_on / ".claude" / "settings.json").read_text()
    assert "PreToolUse" in settings
    assert "pyarnes_pre_tool.py" in settings
