"""Smoke-test the Copier template against the current working tree.

Renders the template into a scratch directory with default answers,
asserts the expected structure, and checks that pyproject.toml has
the five git-URL workspace deps.

Replaces the bash script ``scripts/smoke-template.sh`` — same checks,
expressed in Python with the ``sh`` library for the shell-out points.
``copier`` and ``sh`` are PEP 723 deps so this plugin works without
either being in the project's main venv.

Usage:
    uv run tasks smoke_template               # render to /tmp/pyarnes-smoke
    uv run tasks smoke_template -- /my/dest   # custom destination
"""

# /// script
# requires-python = ">=3.13"
# dependencies = ["sh>=2.0", "copier>=9.0"]
# ///

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

REQUIRED_FILES = (
    "pyproject.toml",
    "README.md",
    "CLAUDE.md",
    "LICENSE",
    "mkdocs.yml",
    ".python-version",
    ".gitignore",
    ".markdownlint.yaml",
    ".yamllint.yaml",
    "docs/index.md",
    "docs/getting-started/installation.md",
    "docs/getting-started/quickstart.md",
    "docs/development/tasks.md",
    "plugins/lint.py",
    "plugins/test.py",
)

FORBIDDEN_PATHS = (
    "packages",
    "specs",
    "template",
    "copier.yml",
)

WORKSPACE_PACKAGES = ("core", "harness", "guardrails", "bench", "tasks")


def _project_root() -> Path:
    """Walk up from this file to find the repo root (pyproject.toml)."""
    here = Path(__file__).resolve().parent
    for candidate in [here, *here.parents]:
        if (candidate / "pyproject.toml").is_file() and (candidate / "copier.yml").is_file():
            return candidate
    msg = "Could not find repo root (no pyproject.toml + copier.yml ancestor)"
    raise RuntimeError(msg)


def _render(repo_root: Path, dest: Path, project_name: str, project_description: str) -> None:
    """Render the Copier template via the ``copier`` CLI in this script's venv."""
    import sh  # noqa: PLC0415

    if dest.exists():
        shutil.rmtree(dest)
    sh.copier(
        "copy",
        "--defaults",
        "--trust",  # the template uses `_tasks:` (post-scaffold hook); requires opt-in
        "--data",
        f"project_name={project_name}",
        "--data",
        f"project_description={project_description}",
        str(repo_root),
        str(dest),
        _out=sys.stdout,
        _err=sys.stderr,
    )


def _structural_checks(dest: Path, project_module: str) -> int:
    """Assert required files exist and forbidden paths are absent."""
    failures = 0
    print("\n━━━ Structural assertions ━━━")  # noqa: T201

    for relpath in (*REQUIRED_FILES, f"src/{project_module}/__init__.py"):
        if (dest / relpath).exists():
            print(f"  ok     {relpath}")  # noqa: T201
        else:
            print(f"  FAIL   missing: {relpath}")  # noqa: T201
            failures += 1

    for relpath in FORBIDDEN_PATHS:
        if not (dest / relpath).exists():
            print(f"  ok     (absent) {relpath}")  # noqa: T201
        else:
            print(f"  FAIL   unexpected: {relpath}")  # noqa: T201
            failures += 1

    return failures


def _pyproject_checks(dest: Path) -> int:
    """Spot-check the rendered pyproject.toml for the five git-URL deps."""
    failures = 0
    print("\n━━━ pyproject.toml content check ━━━")  # noqa: T201
    pyproject = (dest / "pyproject.toml").read_text(encoding="utf-8")

    for pkg in WORKSPACE_PACKAGES:
        pattern = rf"pyarnes-{pkg}\s*@\s*git\+https.*#subdirectory=packages/{pkg}"
        if re.search(pattern, pyproject):
            print(f"  ok     pyarnes-{pkg} git URL present")  # noqa: T201
        else:
            print(f"  FAIL   pyarnes-{pkg} git URL missing from pyproject.toml")  # noqa: T201
            failures += 1

    if re.search(r"^\s*authors\s*=", pyproject, flags=re.MULTILINE):
        print("  FAIL   pyproject.toml should not define an 'authors' field")  # noqa: T201
        failures += 1
    else:
        print("  ok     (absent) 'authors = …' field")  # noqa: T201

    return failures


def _run_smoke_template(argv: list[str]) -> int:
    """Render the template and run the structural + content checks."""
    repo_root = _project_root()
    dest = Path(argv[0]) if argv else Path("/tmp/pyarnes-smoke")  # noqa: S108
    project_name = os.environ.get("PROJECT_NAME", "pyarnes-smoke")
    project_description = os.environ.get("PROJECT_DESCRIPTION", "Smoke-test project")
    project_module = project_name.replace("-", "_")

    print("━━━ pyarnes template smoke test ━━━")  # noqa: T201
    print(f"  source:  {repo_root}")  # noqa: T201
    print(f"  dest:    {dest}")  # noqa: T201
    print(f"  project: {project_name}")  # noqa: T201

    _render(repo_root, dest, project_name, project_description)
    failures = _structural_checks(dest, project_module) + _pyproject_checks(dest)

    print()  # noqa: T201
    if failures:
        print("━━━ SMOKE TEST FAILED ━━━")  # noqa: T201
        return 1
    print("━━━ SMOKE TEST PASSED ━━━")  # noqa: T201
    print(f"\nNext steps (require pushed commits):\n  cd {dest}\n  uv sync\n  uv run tasks check")  # noqa: T201
    return 0


try:
    from pyarnes_tasks.plugin_base import ScriptPlugin

    class SmokeTemplate(ScriptPlugin):
        """``uv run tasks smoke_template`` — render the Copier template and verify."""

        name = "smoke_template"
        description = "Render the Copier template and run structural assertions"

        def run_script(self, argv: list[str]) -> int:
            """Forward to ``_run_smoke_template``."""
            return _run_smoke_template(argv)
except ImportError:
    pass


if __name__ == "__main__":
    raise SystemExit(_run_smoke_template(sys.argv[1:]))
