"""CLI entry-point for the cross-platform task runner.

Every task is a thin wrapper around ``subprocess.run`` so it works
identically on Linux, macOS, and Windows with ``uv run tasks <name>``.
"""

from __future__ import annotations

import subprocess
import sys
from typing import NoReturn

# ── Task definitions ──────────────────────────────────────────────────────
# Each value is the command list passed to subprocess.run.
# Using sys.executable ensures we invoke the right Python/uv environment.

TASKS: dict[str, list[str]] = {
    "lint": [sys.executable, "-m", "ruff", "check", "src", "tests", "packages"],
    "lint:fix": [sys.executable, "-m", "ruff", "check", "--fix", "src", "tests", "packages"],
    "format": [sys.executable, "-m", "ruff", "format", "src", "tests", "packages"],
    "format:check": [sys.executable, "-m", "ruff", "format", "--check", "src", "tests", "packages"],
    "typecheck": [sys.executable, "-m", "ty", "check", "src"],
    "test": [sys.executable, "-m", "pytest"],
    "test:cov": [sys.executable, "-m", "pytest", "--cov", "--cov-report=term-missing"],
    "test:watch": [sys.executable, "-m", "pytest_watch"],
    "watch": [sys.executable, "-m", "pytest_watch"],
    "security": [sys.executable, "-m", "bandit", "-r", "src", "-c", "pyproject.toml"],
    "pylint": [sys.executable, "-m", "pylint", "src/pyarnes"],
    "radon:cc": [
        sys.executable, "-m", "radon", "cc", "src", "packages",
        "--min", "B", "--average", "--total-average", "--no-assert",
    ],
    "radon:mi": [
        sys.executable, "-m", "radon", "mi", "src", "packages",
        "--min", "B",
    ],
    "vulture": [sys.executable, "-m", "vulture", "src", "packages", "--min-confidence", "80"],
    "profile": [sys.executable, "-m", "pyinstrument"],
    "md-lint": [sys.executable, "-m", "pymarkdown", "scan", "."],
    "md-format": [sys.executable, "-m", "mdformat", "."],
    "yaml-lint": [sys.executable, "-m", "yamllint", "."],
    "docs": [sys.executable, "-m", "doq", "-w", "-r", "src"],
    "docs:serve": [sys.executable, "-m", "mkdocs", "serve"],
    "docs:build": [sys.executable, "-m", "mkdocs", "build"],
}


def _print_help() -> None:
    """Print available tasks."""
    print("pyarnes task runner — replaces Make (cross-platform)\n")  # noqa: T201
    print("Usage: uv run tasks <task>\n")  # noqa: T201
    print("Available tasks:")  # noqa: T201
    for name in sorted(TASKS):
        cmd_str = " ".join(TASKS[name])
        print(f"  {name:<16} → {cmd_str}")  # noqa: T201
    print()  # noqa: T201
    # Composite tasks
    print("Composite tasks:")  # noqa: T201
    print("  check            → lint + typecheck + test")  # noqa: T201
    print("  ci               → format:check + lint + typecheck + test:cov + security")  # noqa: T201
    print("  complexity       → radon:cc + radon:mi")  # noqa: T201


COMPOSITE_TASKS: dict[str, list[str]] = {
    "check": ["lint", "typecheck", "test"],
    "ci": ["format:check", "lint", "typecheck", "test:cov", "security"],
    "complexity": ["radon:cc", "radon:mi"],
}


def _run_task(name: str) -> int:
    """Run a single task by name, returning the exit code."""
    if name in COMPOSITE_TASKS:
        for sub in COMPOSITE_TASKS[name]:
            code = _run_task(sub)
            if code != 0:
                return code
        return 0

    cmd = TASKS.get(name)
    if cmd is None:
        print(f"Unknown task: {name}", file=sys.stderr)  # noqa: T201
        _print_help()
        return 1

    print(f"\n{'─' * 60}")  # noqa: T201
    print(f"  ▶ {name}")  # noqa: T201
    print(f"{'─' * 60}\n")  # noqa: T201
    return subprocess.run(cmd, check=False).returncode  # noqa: S603


def main() -> NoReturn:
    """Entry-point: ``uv run tasks <task> [task …]``."""
    args = sys.argv[1:]
    if not args or args[0] in {"--help", "-h", "help"}:
        _print_help()
        raise SystemExit(0)

    for task_name in args:
        code = _run_task(task_name)
        if code != 0:
            raise SystemExit(code)
    raise SystemExit(0)
