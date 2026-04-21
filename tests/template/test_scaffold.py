"""Copier template smoke tests — one per ``adopter_shape``.

``uvx copier copy`` against a pinned ref must produce a working adopter
project for every shape. The ``run_copy``/``source_dir`` fixtures live
in ``conftest.py``.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest


def _project_dependencies(dest: Path) -> list[str]:
    """Return the parsed ``[project.dependencies]`` list from ``dest/pyproject.toml``."""
    data = tomllib.loads((dest / "pyproject.toml").read_text())
    return list(data.get("project", {}).get("dependencies", []))


FORBIDDEN_RUNTIME_DEPS = (
    "pyarnes-core",
    "pyarnes-harness",
    "pyarnes-guardrails",
    "pyarnes-bench",
    "presidio-analyzer",
    "kreuzberg",
    "boto3",
    "httpx",
    "pydantic",
)


@pytest.mark.parametrize(
    "shape",
    ["blank", "pii-redaction", "s3-sweep", "rtm-toggl-agile"],
)
def test_scaffold_generates(shape: str, run_copy, tmp_path: Path) -> None:
    """Every adopter shape renders a minimum viable file tree.

    Runtime ``src/<module>/`` stays plain Python (no pyarnes, no shape-libs).
    Agent scaffolding lives under ``.claude/agent_kit/``; pyarnes lands in
    ``[dependency-groups.dev]``.
    """
    dest = run_copy(
        tmp_path / f"scaffold-{shape}",
        project_name=f"scaffold-{shape}",
        project_description=f"scaffold smoke for {shape}",
        adopter_shape=shape,
    )

    module_dir = dest / "src" / f"scaffold_{shape.replace('-', '_')}"
    agent_kit = dest / ".claude" / "agent_kit"
    assert (dest / "pyproject.toml").is_file()
    assert (dest / "CLAUDE.md").is_file()
    assert (dest / "AGENTS.md").is_file()
    # Runtime src/ is plain Python — only cli.py and __init__.py.
    assert (module_dir / "cli.py").is_file()
    assert (module_dir / "__init__.py").is_file()
    assert not (module_dir / "pipeline.py").exists()
    assert not (module_dir / "guardrails.py").exists()
    assert not (module_dir / "tools").exists()
    # Agent scaffolding relocated under .claude/agent_kit/.
    assert (agent_kit / "pipeline.py").is_file()
    assert (agent_kit / "guardrails.py").is_file()
    assert (agent_kit / "tools" / "__init__.py").is_file()
    assert (agent_kit / "README.md").is_file()

    # CLAUDE.md defers to AGENTS.md as the shared source of truth.
    claude = (dest / "CLAUDE.md").read_text()
    assert "AGENTS.md" in claude

    pyproject = (dest / "pyproject.toml").read_text()
    assert "pyarnes-core" in pyproject  # now in dev group, still present
    assert "[project.scripts]" in pyproject
    assert f"scaffold_{shape.replace('-', '_')}.cli:app" in pyproject


@pytest.mark.parametrize(
    ("shape", "script_path", "inline_dep"),
    [
        ("pii-redaction", "scripts/examples/pii-redaction/extract-pdf.py", "kreuzberg"),
        ("s3-sweep", "scripts/examples/s3-sweep/list-bucket.py", "boto3"),
        ("rtm-toggl-agile", "scripts/examples/rtm-toggl-agile/fetch-entries.py", "httpx"),
    ],
)
def test_shape_specific_deps_are_pep723_inline(
    shape: str,
    script_path: str,
    inline_dep: str,
    run_copy,
    tmp_path: Path,
) -> None:
    """Shape-specific libs appear as PEP 723 inline metadata — not in pyproject.toml."""
    dest = run_copy(
        tmp_path / f"scaffold-inline-{shape}",
        project_name=f"scaffold-inline-{shape}",
        project_description=f"inline deps for {shape}",
        adopter_shape=shape,
    )
    # No shape-lib (and no pyarnes) may appear in [project.dependencies].
    deps_text = "\n".join(_project_dependencies(dest))
    for forbidden in FORBIDDEN_RUNTIME_DEPS:
        assert forbidden not in deps_text

    # The shape's example script carries its own PEP 723 header declaring the lib.
    script = (dest / script_path).read_text()
    assert "# /// script" in script
    assert "# ///" in script
    assert inline_dep in script


@pytest.mark.parametrize(
    "shape",
    ["blank", "pii-redaction", "s3-sweep", "rtm-toggl-agile"],
)
def test_project_dependencies_stay_minimal(shape: str, run_copy, tmp_path: Path) -> None:
    """``[project.dependencies]`` holds only utility libs — no pyarnes, no shape-libs."""
    dest = run_copy(
        tmp_path / f"scaffold-deps-{shape}",
        project_name=f"scaffold-deps-{shape}",
        project_description=f"deps check for {shape}",
        adopter_shape=shape,
    )
    deps_text = "\n".join(_project_dependencies(dest))
    for forbidden in FORBIDDEN_RUNTIME_DEPS:
        assert forbidden not in deps_text, f"{forbidden} leaked into [project.dependencies] for {shape}"
    # Utility libs are still there.
    for expected in ("loguru", "returns", "toolz", "typer"):
        assert expected in deps_text


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
