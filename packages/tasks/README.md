# pyarnes-tasks

Minimal package stub for the current multi-package pyarnes monorepo.

Current scope: dev-time task runner used by the monorepo and template.

Canonical docs:
- [Root README](../../README.md)
- [Tooling artifacts and repo hygiene](../../specs/consolidation/15-tooling-artifacts.md)

Quick usage:
- Run `uv run tasks help` for the current task list.
- Configure paths in `[tool.pyarnes-tasks]` inside `pyproject.toml`.

This file stays intentionally short because `packages/tasks/pyproject.toml` still uses it as the package readme.
