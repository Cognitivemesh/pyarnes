# pyarnes-tasks

Cross-platform task runner. Replaces Make for the pyarnes monorepo and
the projects scaffolded from its Copier template.

## Quick usage

```bash
uv run tasks help                  # list every registered plugin, grouped by kind
uv run tasks check                 # composite: lint -> typecheck -> test
uv run tasks ci                    # composite: format:check + lint + typecheck + test:cov + security
uv run tasks <name> -- extra args  # `--` forwards everything after to the last task
```

## Architecture

`pyarnes-tasks` is a thin loader. Every task lives in a Python file
under `/plugins/` (configurable via `[tool.pyarnes-tasks].plugin_dirs`).

- **`Plugin` ABC** (`plugin_base.py`) bakes in observability (JSONL
  events via `loguru`), wall-time perf, error-taxonomy mapping, missing
  binary preflight, and self-registration via `__init_subclass__`.
- Four kind-specific bases — `ShellPlugin`, `ScriptPlugin`,
  `ModulePlugin`, `CompositePlugin` — pick the execution strategy
  internally. Authors only fill in `name`, `description`, and the kind's
  declarative attributes (`cmd` / `subtasks` / `call`).
- **`PluginRegistry`** (`registry.py`) holds the discovered plugins.
- **`load_plugins`** (`plugin_loader.py`) walks `/plugins/`, imports
  each file, and side-effect registers via `Plugin.__init_subclass__`.
- The CLI (`cli.py`) dispatches `uv run tasks <name>` to
  `registry.get(name).run(extra, cwd)`.

## Writing a plugin

The minimum SHELL plugin:

```python
"""Lint via ruff."""
from __future__ import annotations
from pyarnes_tasks.plugin_base import ShellPlugin

class Lint(ShellPlugin):
    name = "lint"
    description = "ruff check across sources and tests"
    cmd = ("uv", "run", "ruff", "check")
    targets = ("sources", "tests")   # expanded against [tool.pyarnes-tasks]
```

Drop that file into `/plugins/`. `uv run tasks lint` works on next
invocation.

## SCRIPT plugins (PEP 723)

Tasks that need their own deps without polluting the project venv use
the `SCRIPT` kind with PEP 723 inline metadata. Heavy imports must live
inside `run_script` (or a top-level helper called from it) so the
parent process can import the file for registration without those deps
installed:

```python
"""AST refactor via Bowler."""
# /// script
# requires-python = ">=3.13"
# dependencies = ["bowler>=0.9"]
# ///
from __future__ import annotations
import sys

def _run_refactor(argv):
    from bowler import Query  # lazy — only imported under `uv run`
    Query(argv).select_function("...").rename("...").execute()
    return 0

try:
    from pyarnes_tasks.plugin_base import ScriptPlugin

    class Refactor(ScriptPlugin):
        name = "refactor"
        description = "Bowler-driven safe rewrites"

        def run_script(self, argv):
            return _run_refactor(argv)
except ImportError:
    pass

if __name__ == "__main__":
    raise SystemExit(_run_refactor(sys.argv[1:]))
```

The `try/except ImportError` block protects against the ephemeral PEP
723 venv (where `pyarnes_tasks` isn't installed) — the registration
silently skips, and the `__main__` block does the work.

## Configuration

```toml
# pyproject.toml
[tool.pyarnes-tasks]
sources = ["packages"]      # passed in for `targets = ("sources",)`
tests = ["tests"]           # passed in for `targets = ("tests",)`
plugin_dirs = ["plugins"]   # default — relative to project root
```

## Canonical docs

- [Root README](../../README.md)
- [Tooling artifacts and repo hygiene](../../specs/consolidation/15-tooling-artifacts.md)
