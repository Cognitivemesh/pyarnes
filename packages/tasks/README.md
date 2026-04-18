# pyarnes-tasks

Cross-platform task runner for pyarnes-based projects — replaces `make` with `uv run tasks <name>`.

## How it works

`pyarnes-tasks` reads per-project configuration from `pyproject.toml`:

```toml
[tool.pyarnes-tasks]
sources = ["src"]              # directories passed to ruff / ty / bandit / radon / vulture
tests = ["tests"]              # pytest test directories (silently skipped if missing)
packages = []                  # extra roots; set this for monorepos (e.g. ["packages"])
```

All paths are resolved relative to `pyproject.toml`. Missing paths are dropped from the command line without failure — so a brand-new project with no `tests/` still gets a working `uv run tasks test`.

## Available tasks

| Task | Description |
|---|---|
| `uv run tasks lint` | Ruff lint on sources + tests + packages |
| `uv run tasks lint:fix` | Ruff lint with auto-fix |
| `uv run tasks format` | Ruff format |
| `uv run tasks format:check` | Check formatting |
| `uv run tasks typecheck` | `ty` type check |
| `uv run tasks test` | pytest |
| `uv run tasks test:cov` | pytest with coverage |
| `uv run tasks watch` | pytest-watch (TDD) |
| `uv run tasks security` | bandit |
| `uv run tasks pylint` | pylint (custom rules only) |
| `uv run tasks radon:cc` | cyclomatic complexity |
| `uv run tasks radon:mi` | maintainability index |
| `uv run tasks vulture` | dead-code detection |
| `uv run tasks md-lint` / `md-format` / `yaml-lint` | markdown & yaml housekeeping |
| `uv run tasks docs` / `docs:serve` / `docs:build` | docstring generation + mkdocs |
| `uv run tasks check` | lint + typecheck + test |
| `uv run tasks ci` | format:check + lint + typecheck + test:cov + security |
| `uv run tasks complexity` | radon:cc + radon:mi |
