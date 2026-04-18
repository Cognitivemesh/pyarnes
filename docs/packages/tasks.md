# pyarnes-tasks

Cross-platform task runner — replaces `make` with `uv run tasks <name>`. Shared between the pyarnes monorepo and every project bootstrapped from the template.

## Entry point

`pyarnes-tasks` registers a single console script, `tasks`, via `[project.scripts]`. Both inside the pyarnes repo and inside template-generated projects, you invoke it the same way:

```bash
uv run tasks help
uv run tasks check
uv run tasks watch
```

## Configuration

The task runner is driven by a `[tool.pyarnes-tasks]` block in the nearest `pyproject.toml`:

```toml
[tool.pyarnes-tasks]
sources = ["src"]          # code roots — ruff / ty / bandit / radon / vulture targets
tests = ["tests"]           # pytest test roots (silently skipped when missing)
```

### Monorepo usage (pyarnes itself)

```toml
[tool.pyarnes-tasks]
sources = ["packages"]
tests = ["tests"]
```

### Template-generated project usage

```toml
[tool.pyarnes-tasks]
sources = ["src"]
tests = ["tests"]
```

Missing directories are dropped automatically — a freshly scaffolded project with no `tests/` directory still gets a working `uv run tasks check`. Pytest exit code 5 (`no tests collected`) is treated as success for the `test` family of tasks.

## Tasks

| Task | What it runs |
|---|---|
| `lint` | `ruff check <sources + tests>` |
| `lint:fix` | `ruff check --fix <sources + tests>` |
| `format` | `ruff format <sources + tests>` |
| `format:check` | `ruff format --check <sources + tests>` |
| `typecheck` | `ty check <sources>` |
| `test` | `pytest <tests>` (no-op if no tests) |
| `test:cov` | `pytest <tests> --cov --cov-report=term-missing` |
| `watch` / `test:watch` | `pytest-watch <tests>` |
| `security` | `bandit -r <sources> -c pyproject.toml` |
| `pylint` | `pylint <sources>` (custom rules only, complements ruff) |
| `radon:cc` | Cyclomatic complexity (filtered to ≥ B) |
| `radon:mi` | Maintainability index (filtered to ≥ B) |
| `vulture` | Dead-code detection (min confidence 80) |
| `profile` | `pyinstrument` |
| `md-lint` / `md-format` | `pymarkdown scan .` / `mdformat .` |
| `yaml-lint` | `yamllint .` |
| `docs` | `doq -w -r <sources>` (docstring generation) |
| `docs:serve` / `docs:build` | `mkdocs serve` / `mkdocs build` |
| `update` | `uvx copier update` — pulls latest template improvements |

### Composites

| Task | Combines |
|---|---|
| `check` | `lint` + `typecheck` + `test` |
| `ci` | `format:check` + `lint` + `typecheck` + `test:cov` + `security` |
| `complexity` | `radon:cc` + `radon:mi` |

## The `update` task

`uv run tasks update` wraps Copier so developers never need to remember its flags. It reads `.copier-answers.yml` (written automatically by `copier copy` when the template is fetched from a real git ref like `gh:Cognitivemesh/pyarnes`), finds the pinned pyarnes ref, and pulls template improvements into the project. Conflicts (if any) are surfaced interactively.

## Source

`pyarnes-tasks` lives in [`packages/tasks/`](https://github.com/Cognitivemesh/pyarnes/tree/main/packages/tasks) inside the pyarnes monorepo. Template-generated projects install it as a git-URL dependency alongside the other four pyarnes-* packages.
