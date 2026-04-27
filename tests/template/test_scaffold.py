"""Copier template smoke tests — one per ``adopter_shape``.

``uvx copier copy`` against a pinned ref must produce a working adopter
project for every shape. The ``run_copy``/``source_dir`` fixtures live
in ``conftest.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "shape",
    ["blank", "pii-redaction", "s3-sweep", "rtm-toggl-agile"],
)
def test_scaffold_generates(shape: str, run_copy, tmp_path: Path) -> None:
    """Every adopter shape renders a minimum viable file tree."""
    dest = run_copy(
        tmp_path / f"scaffold-{shape}",
        project_name=f"scaffold-{shape}",
        project_description=f"scaffold smoke for {shape}",
        adopter_shape=shape,
    )

    module_dir = dest / "src" / f"scaffold_{shape.replace('-', '_')}"
    assert (dest / "pyproject.toml").is_file()
    assert (dest / "CLAUDE.md").is_file()
    assert (dest / "AGENTS.md").is_file()
    assert (module_dir / "pipeline.py").is_file()
    assert (module_dir / "cli.py").is_file()
    assert (module_dir / "guardrails.py").is_file()
    assert (module_dir / "tools" / "__init__.py").is_file()

    # CLAUDE.md defers to AGENTS.md as the shared source of truth.
    claude = (dest / "CLAUDE.md").read_text()
    assert "AGENTS.md" in claude

    pyproject = (dest / "pyproject.toml").read_text()
    assert "pyarnes-core" in pyproject
    assert "[project.scripts]" in pyproject
    assert f"scaffold_{shape.replace('-', '_')}.cli:app" in pyproject


def test_shape_specific_deps(run_copy, tmp_path: Path) -> None:
    """Shape-specific runtime deps land in the generated pyproject.toml."""
    dest = run_copy(
        tmp_path / "scaffold-deps-pii",
        project_name="scaffold-deps-pii",
        project_description="pii deps",
        adopter_shape="pii-redaction",
    )
    pyproject = (dest / "pyproject.toml").read_text()
    assert "presidio-analyzer" in pyproject
    assert "kreuzberg" in pyproject


def test_blank_has_no_shape_specific_deps(run_copy, tmp_path: Path) -> None:
    """Blank shape keeps the dependency list minimal."""
    dest = run_copy(
        tmp_path / "scaffold-deps-blank",
        project_name="scaffold-deps-blank",
        project_description="blank deps",
        adopter_shape="blank",
    )
    pyproject = (dest / "pyproject.toml").read_text()
    assert "presidio-analyzer" not in pyproject
    assert "boto3" not in pyproject
    assert "httpx" not in pyproject


def test_dev_hooks_ship_only_when_enabled(run_copy, tmp_path: Path) -> None:
    """``.claude/hooks/`` and ``tests/bench/`` appear iff ``enable_dev_hooks`` is true."""
    dest_off = run_copy(
        tmp_path / "no-hooks",
        project_name="no-hooks",
        project_description="hooks off",
        adopter_shape="blank",
        enable_dev_hooks=False,
    )
    assert not (dest_off / ".claude" / "hooks" / "pyarnes_pre_tool.py").exists()
    assert not (dest_off / ".claude" / "settings.json").exists()
    assert not (dest_off / "tests" / "bench").exists()

    dest_on = run_copy(
        tmp_path / "with-hooks",
        project_name="with-hooks",
        project_description="hooks on",
        adopter_shape="rtm-toggl-agile",
        enable_dev_hooks=True,
    )
    assert (dest_on / ".claude" / "hooks" / "pyarnes_pre_tool.py").is_file()
    assert (dest_on / ".claude" / "hooks" / "pyarnes_post_tool.py").is_file()
    assert (dest_on / ".claude" / "hooks" / "pyarnes_stop.py").is_file()
    assert (dest_on / ".claude" / "hooks" / "pyarnes_session_start.py").is_file()
    assert (dest_on / ".claude" / "hooks" / "pyarnes_session_end.py").is_file()
    assert (dest_on / ".claude" / "settings.json").is_file()
    assert (dest_on / "tests" / "bench" / "test_agent_quality.py").is_file()

    settings = (dest_on / ".claude" / "settings.json").read_text()
    for hook_event in ("PreToolUse", "PostToolUse", "Stop", "SessionStart", "SessionEnd"):
        assert hook_event in settings
    for hook_script in (
        "pyarnes_pre_tool.py",
        "pyarnes_post_tool.py",
        "pyarnes_stop.py",
        "pyarnes_session_start.py",
        "pyarnes_session_end.py",
    ):
        assert hook_script in settings

    # The pre-tool script pulls in every new guardrail class.
    pre_hook = (dest_on / ".claude" / "hooks" / "pyarnes_pre_tool.py").read_text()
    for guardrail_class in (
        "SecretLeakGuardrail",
        "NetworkEgressGuardrail",
        "RateLimitGuardrail",
    ):
        assert guardrail_class in pre_hook
