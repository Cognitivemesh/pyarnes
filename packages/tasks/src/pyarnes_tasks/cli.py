"""Cross-platform task runner — replaces Make.

Tasks are built dynamically from ``[tool.pyarnes-tasks]`` in the nearest
``pyproject.toml``. See ``packages/tasks/README.md`` for the full reference.

Missing paths are dropped from each command line, so a fresh project with no
``tests/`` directory still gets a working ``uv run tasks check``.
"""

from __future__ import annotations

import subprocess  # nosec B404
import sys
import tomllib
from pathlib import Path
from typing import NoReturn

DEFAULT_SOURCES = ["src"]
DEFAULT_TESTS = ["tests"]

# Tasks that run pytest collection — pytest exit code 5 ("no tests collected")
# is treated as success for these, so an empty tests/ directory doesn't fail
# `uv run tasks check`. pytest-watch variants restart rather than exiting 5,
# so they're excluded.
_PYTEST_COLLECTION_TASKS = frozenset({"test", "test:cov"})
_PYTEST_NO_TESTS_EXIT_CODE = 5

COMPOSITE_TASKS: dict[str, list[str]] = {
    "check": ["lint", "typecheck", "test"],
    "ci": ["format:check", "lint", "typecheck", "test:cov", "security"],
    "complexity": ["radon:cc", "radon:mi"],
}


def _find_pyproject() -> Path | None:
    """Walk up from cwd looking for ``pyproject.toml``."""
    cwd = Path.cwd()
    for candidate in [cwd, *cwd.parents]:
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file():
            return pyproject
    return None


def _load_config() -> tuple[list[str], list[str], Path]:
    """Return ``(sources, tests, project_root)``."""
    pyproject = _find_pyproject()
    if pyproject is None:
        return DEFAULT_SOURCES, DEFAULT_TESTS, Path.cwd()
    with pyproject.open("rb") as fh:
        data = tomllib.load(fh)
    tool = data.get("tool", {}).get("pyarnes-tasks", {})
    sources = list(tool.get("sources", DEFAULT_SOURCES))
    tests = list(tool.get("tests", DEFAULT_TESTS))
    return sources, tests, pyproject.parent


def _existing(paths: list[str], root: Path) -> list[str]:
    """Return the subset of ``paths`` that exist (as file or dir) under ``root``."""
    return [p for p in paths if (root / p).exists()]


def _build_tasks() -> tuple[dict[str, list[str]], Path]:
    sources, tests, root = _load_config()
    sources = _existing(sources, root)
    tests = _existing(tests, root)

    code_targets = sources or ["."]
    lint_targets = sources + tests or ["."]
    py = sys.executable
    pyproject_path = str(root / "pyproject.toml")

    tasks: dict[str, list[str]] = {
        "update": ["uvx", "copier", "update"],
        "lint": [py, "-m", "ruff", "check", *lint_targets],
        "lint:fix": [py, "-m", "ruff", "check", "--fix", *lint_targets],
        "format": [py, "-m", "ruff", "format", *lint_targets],
        "format:check": [py, "-m", "ruff", "format", "--check", *lint_targets],
        "typecheck": [py, "-m", "ty", "check", *code_targets],
        "security": [py, "-m", "bandit", "-r", *code_targets, "-c", pyproject_path],
        "pylint": [py, "-m", "pylint", *code_targets],
        "radon:cc": [
            py,
            "-m",
            "radon",
            "cc",
            *code_targets,
            "--min",
            "B",
            "--average",
            "--total-average",
            "--no-assert",
        ],
        "radon:mi": [py, "-m", "radon", "mi", *code_targets, "--min", "B"],
        "vulture": [py, "-m", "vulture", *code_targets, "--min-confidence", "80"],
        "profile": [py, "-m", "pyinstrument"],
        "md-lint": [py, "-m", "pymarkdown", "scan", "."],
        "md-format": [py, "-m", "mdformat", "."],
        "yaml-lint": [py, "-m", "yamllint", "."],
        "docs": [py, "-m", "doq", "-w", "-r", *code_targets],
        "docs:serve": [py, "-m", "mkdocs", "serve"],
        "docs:build": [py, "-m", "mkdocs", "build"],
        "check:redirects": [py, str(root / "scripts" / "check_redirects.py")],
        # Graph tools (opt-in group: `uv sync --group graph` first).
        "graph:render": ["graphify", "."],
        "graph:blast": ["code-review-graph", "blast"],
        # Bench: drive a pyarnes-bench EvalSuite and read back the JSONL log.
        "bench:run": [py, "-m", "pyarnes_tasks.bench_run"],
        "bench:report": [py, "-m", "pyarnes_tasks.bench_report"],
        # Burn: token cost report across AI coding sessions.
        "burn:report": [py, "-m", "pyarnes_tasks.burn_report"],
        # Codeburn: KPIs, model comparison, and waste-detection scan.
        "codeburn:kpis":     [py, "-m", "pyarnes_tasks.codeburn_kpis"],
        "codeburn:compare":  [py, "-m", "pyarnes_tasks.codeburn_compare"],
        "codeburn:optimize": [py, "-m", "pyarnes_tasks.codeburn_optimize"],
        # Observer: stream and filter structured JSONL logs.
        "observer:tail": [py, "-m", "pyarnes_tasks.observer_tail"],
        "observer:filter": [py, "-m", "pyarnes_tasks.observer_filter"],
    }

    if tests:
        tasks["test"] = [py, "-m", "pytest", *tests]
        tasks["test:cov"] = [py, "-m", "pytest", *tests, "--cov", "--cov-report=term-missing"]
        tasks["test:watch"] = [py, "-m", "pytest_watch", *tests]
        tasks["watch"] = [py, "-m", "pytest_watch", *tests]
    else:
        # No tests/ yet — emit a friendly no-op so `uv run tasks check` still succeeds
        # on a freshly-scaffolded project. The python-test skill scaffolds real tests.
        msg = "No tests found. Ask Claude Code: 'write a test for <X>' to scaffold one."
        noop = [py, "-c", f"print({msg!r})"]
        for name in ("test", "test:cov", "test:watch", "watch"):
            tasks[name] = noop

    return tasks, root


def _print_help(tasks: dict[str, list[str]]) -> None:
    print("pyarnes task runner — replaces Make (cross-platform)\n")  # noqa: T201
    print("Usage: uv run tasks <task> [task ...]\n")  # noqa: T201
    print("Available tasks:")  # noqa: T201
    for name in sorted(tasks):
        cmd_str = " ".join(tasks[name])
        print(f"  {name:<16} -> {cmd_str}")  # noqa: T201
    print()  # noqa: T201
    print("Composite tasks:")  # noqa: T201
    for comp, parts in COMPOSITE_TASKS.items():
        print(f"  {comp:<16} -> {' + '.join(parts)}")  # noqa: T201


def _run_task(name: str, tasks: dict[str, list[str]], root: Path, extra: tuple[str, ...] = ()) -> int:
    # Composite tasks ignore `extra` — they dispatch to sub-tasks that each take their own args.
    if name in COMPOSITE_TASKS:
        for sub in COMPOSITE_TASKS[name]:
            code = _run_task(sub, tasks, root)
            if code != 0:
                return code
        return 0

    cmd = tasks.get(name)
    if cmd is None:
        print(f"Unknown task: {name}", file=sys.stderr)  # noqa: T201
        _print_help(tasks)
        return 1

    print(f"\n{'─' * 60}")  # noqa: T201
    print(f"  ▶ {name}")  # noqa: T201
    print(f"{'─' * 60}\n")  # noqa: T201
    code = subprocess.run([*cmd, *extra], check=False, cwd=root).returncode  # noqa: S603  # nosec B603
    if name in _PYTEST_COLLECTION_TASKS and code == _PYTEST_NO_TESTS_EXIT_CODE:
        return 0
    return code


def main() -> NoReturn:
    """Entry-point: ``uv run tasks <task> [task ...] [-- extra-args]``.

    ``--`` forwards everything after it to the last task.
    """
    tasks, root = _build_tasks()
    args = sys.argv[1:]
    if not args or args[0] in {"--help", "-h", "help"}:
        _print_help(tasks)
        raise SystemExit(0)

    try:
        sep = args.index("--")
    except ValueError:
        task_names, extra = args, ()
    else:
        task_names, extra = args[:sep], tuple(args[sep + 1 :])

    last = len(task_names) - 1
    for i, task_name in enumerate(task_names):
        code = _run_task(task_name, tasks, root, extra if i == last else ())
        if code != 0:
            raise SystemExit(code)
    raise SystemExit(0)
