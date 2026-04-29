"""Cross-platform task runner — replaces Make.

Tasks are discovered from ``/plugins/`` (configurable via
``[tool.pyarnes-tasks].plugin_dirs``). Each plugin is a Python file that
subclasses one of :class:`ShellPlugin` / :class:`ScriptPlugin` /
:class:`ModulePlugin` / :class:`CompositePlugin` from
:mod:`pyarnes_tasks.plugin_base`. The ABC bakes in observability
(JSONL events), perf timing, error-taxonomy mapping, missing-binary
preflight, and self-registration.

Run ``uv run tasks help`` for the registered task list.
"""

from __future__ import annotations

import sys
import tomllib
from collections import defaultdict
from pathlib import Path
from typing import NoReturn

from pyarnes_tasks.plugin_loader import load_plugins
from pyarnes_tasks.registry import global_registry

DEFAULT_PLUGIN_DIRS = ["plugins"]


def _find_pyproject() -> Path | None:
    """Walk up from cwd looking for ``pyproject.toml``."""
    cwd = Path.cwd()
    for candidate in [cwd, *cwd.parents]:
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file():
            return pyproject
    return None


def _project_root() -> Path:
    """Return the directory containing the nearest ``pyproject.toml``."""
    pyproject = _find_pyproject()
    return pyproject.parent if pyproject is not None else Path.cwd()


def _plugin_dirs(root: Path) -> list[Path]:
    """Return the plugin directories declared in ``[tool.pyarnes-tasks]``."""
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return [root / d for d in DEFAULT_PLUGIN_DIRS]
    with pyproject.open("rb") as fh:
        data = tomllib.load(fh)
    tool = data.get("tool", {}).get("pyarnes-tasks", {})
    dirs = list(tool.get("plugin_dirs", DEFAULT_PLUGIN_DIRS))
    return [root / d for d in dirs]


def _print_help() -> None:
    """List every registered plugin, grouped by ``TaskKind``."""
    print("pyarnes task runner — replaces Make (cross-platform)\n")  # noqa: T201
    print("Usage: uv run tasks <task> [task ...] [-- extra-args]\n")  # noqa: T201

    by_kind: dict[str, list] = defaultdict(list)
    registry = global_registry()
    for name in registry.names:
        plugin = registry.get(name)
        if plugin is None:
            continue  # registry.names returned it; race with unregister is impossible here.
        by_kind[str(plugin.kind)].append(plugin)

    for kind in sorted(by_kind):
        print(f"{kind.upper()} tasks:")  # noqa: T201
        for plugin in by_kind[kind]:
            desc = plugin.description or ""
            print(f"  {plugin.name:<20} {desc}")  # noqa: T201
        print()  # noqa: T201


def _dispatch(name: str, root: Path, extra: tuple[str, ...]) -> int:
    """Run the registered plugin under *name*; return its exit code."""
    plugin = global_registry().get(name)
    if plugin is None:
        print(f"Unknown task: {name}", file=sys.stderr)  # noqa: T201
        _print_help()
        return 1
    print(f"\n{'─' * 60}")  # noqa: T201
    print(f"  ▶ {name}")  # noqa: T201
    print(f"{'─' * 60}\n")  # noqa: T201
    return plugin.run(extra, root)


def main() -> NoReturn:
    """Entry-point: ``uv run tasks <task> [task ...] [-- extra-args]``.

    ``--`` forwards everything after it to the last task.
    """
    root = _project_root()
    for plugin_dir in _plugin_dirs(root):
        load_plugins(plugin_dir)

    args = sys.argv[1:]
    if not args or args[0] in {"--help", "-h", "help"}:
        _print_help()
        raise SystemExit(0)

    try:
        sep = args.index("--")
    except ValueError:
        task_names, extra = args, ()
    else:
        task_names, extra = args[:sep], tuple(args[sep + 1 :])

    last = len(task_names) - 1
    for i, task_name in enumerate(task_names):
        code = _dispatch(task_name, root, extra if i == last else ())
        if code != 0:
            raise SystemExit(code)
    raise SystemExit(0)
