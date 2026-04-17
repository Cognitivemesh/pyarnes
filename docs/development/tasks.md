# Task Runner

pyarnes includes a cross-platform task runner that replaces Make.

## Usage

```bash
uv run tasks <task> [task ...]
uv run tasks help    # list all tasks
```

## Available tasks

| Task | Description |
|---|---|
| `lint` | Ruff lint (src + tests + packages) |
| `lint:fix` | Ruff lint with auto-fix |
| `format` | Ruff format |
| `format:check` | Check formatting |
| `typecheck` | ty type checking |
| `test` | Run pytest |
| `test:cov` | pytest with coverage |
| `watch` | TDD watch mode |
| `security` | Bandit security scan |
| `pylint` | Pylint (custom rules) |
| `radon:cc` | Cyclomatic complexity (min B) |
| `radon:mi` | Maintainability index (min B) |
| `vulture` | Dead code detection |
| `docs:serve` | Serve MkDocs locally |
| `docs:build` | Build MkDocs site |

## Composite tasks

| Task | Steps |
|---|---|
| `check` | lint + typecheck + test |
| `ci` | format:check + lint + typecheck + test:cov + security |
| `complexity` | radon:cc + radon:mi |
