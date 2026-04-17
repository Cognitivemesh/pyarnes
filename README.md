# pyarnes

> A minimal agentic harness engineering template for Python.
> It does **not** replace Claude Code, Cursor, or Codex — it **collaborates** with them.

**pyarnes** adds verification loops, safety enforcement, and lifecycle management that AI coding tools miss. It captures raw outputs and errors, feeds that reality back to the model, applies guardrails around what the system can touch, and makes every step visible and debuggable.

## Features

- **Four error types** — transient (retry with backoff), LLM-recoverable (return as ToolMessage), user-fixable (interrupt for human input), and unexpected (bubble up for debugging)
- **Async-first** — built on `asyncio` to maximise performance and avoid GIL contention
- **JSONL observability** — single logging layer via `structlog` that agents can parse
- **Safety guardrails** — composable path, command, and tool-allowlist checks
- **Lifecycle FSM** — INIT → RUNNING → PAUSED → COMPLETED / FAILED with full history
- **Cross-platform task runner** — replaces Make with `uv run tasks <name>`
- **TDD out of the box** — pytest-watch, pytest-bdd (Gherkin), coverage

## Quick start

```bash
# Install dependencies
uv sync

# Run all checks (lint + typecheck + test)
uv run tasks check

# TDD watch mode
uv run tasks watch

# See all available tasks
uv run tasks help
```

## Available tasks

| Task | Description |
|---|---|
| `uv run tasks lint` | Ruff lint |
| `uv run tasks lint:fix` | Ruff lint with auto-fix |
| `uv run tasks format` | Ruff format |
| `uv run tasks format:check` | Check formatting |
| `uv run tasks typecheck` | ty type checking |
| `uv run tasks test` | Run pytest |
| `uv run tasks test:cov` | Run pytest with coverage |
| `uv run tasks watch` | TDD watch mode (pytest-watch) |
| `uv run tasks security` | Bandit security scan |
| `uv run tasks pylint` | Pylint (custom rules only) |
| `uv run tasks md-lint` | Markdown lint |
| `uv run tasks md-format` | Markdown format |
| `uv run tasks yaml-lint` | YAML lint |
| `uv run tasks docs` | Generate docstrings (doq) |
| `uv run tasks check` | lint + typecheck + test |
| `uv run tasks ci` | Full CI pipeline |

## Error taxonomy

```text
┌─────────────────┐    retry (max 2)     ┌─────────────────┐
│ TransientError   │ ──────────────────── │ Tool re-executed │
└─────────────────┘                      └─────────────────┘

┌─────────────────────┐  ToolMessage     ┌─────────────────┐
│ LLMRecoverableError │ ───────────────► │ Model adjusts    │
└─────────────────────┘  (is_error=True) └─────────────────┘

┌─────────────────┐  interrupt           ┌─────────────────┐
│ UserFixableError │ ──────────────────► │ Human input      │
└─────────────────┘                      └─────────────────┘

┌─────────────────┐  bubble up           ┌─────────────────┐
│ UnexpectedError  │ ──────────────────► │ Debug / postmortem│
└─────────────────┘                      └─────────────────┘
```

## Project structure

```text
pyarnes/
├── pyproject.toml              # Central config: uv, ruff, ty, pytest, etc.
├── CLAUDE.md                   # Agent instructions
├── .claude/                    # Claude Code skills, hooks, memory
│   ├── settings.json
│   ├── commands/tdd.md         # TDD Red-Green-Refactor skill
│   ├── hooks/
│   └── memory/
├── src/pyarnes/
│   ├── harness/                # Agent loop, errors, guardrails, lifecycle
│   ├── capture/                # Raw output & error recording
│   ├── observe/                # JSONL structured logging (structlog)
│   ├── tools/                  # Tool registry
│   └── tasks/                  # Cross-platform task runner
└── tests/
    ├── unit/                   # Unit tests
    └── features/               # BDD / Gherkin feature files
```

## Tooling stack

| Category | Tool | Purpose |
|---|---|---|
| Package manager | [uv](https://github.com/astral-sh/uv) | Fast dependency management |
| Linting & formatting | [Ruff](https://docs.astral.sh/ruff/) | Blazing-fast linter + formatter |
| Type checking | [ty](https://github.com/astral-sh/ty) | Fast type checker (Astral) |
| Security | [Bandit](https://bandit.readthedocs.io/) | Security linter (via Ruff S rules + standalone) |
| Taint analysis | [Pyre/Pysa](https://pyre-check.org/docs/pysa-basics/) | Data-flow taint tracking (see note below) |
| Testing | [pytest](https://docs.pytest.org/) | Test framework |
| BDD | [pytest-bdd](https://pytest-bdd.readthedocs.io/) | Gherkin feature files |
| Coverage | [pytest-cov](https://pytest-cov.readthedocs.io/) | Coverage reporting |
| TDD watcher | [pytest-watch](https://github.com/joeyespo/pytest-watch) | Auto-rerun on file changes |
| File watcher | [watchfiles](https://watchfiles.helpmanual.io/) | Generic file change monitoring |
| Custom lint rules | [Pylint](https://pylint.readthedocs.io/) | Complementary rules Ruff doesn't cover |
| Process control | [pexpect](https://pexpect.readthedocs.io/) | Spawn & control child processes |
| Docstrings | [doq](https://github.com/heavenshell/py-doq) | Generate pydoc comments |
| Markdown lint | [pymarkdownlnt](https://github.com/jackdewinter/pymarkdown) | Markdown linter |
| Markdown format | [mdformat](https://mdformat.readthedocs.io/) | CommonMark formatter |
| YAML lint | [yamllint](https://yamllint.readthedocs.io/) | YAML linter |
| Logging | [structlog](https://www.structlog.org/) | JSONL structured logging |

### Note on SonarQube rules

Ruff already implements most SonarQube Python rules through its comprehensive rule sets: `F` (pyflakes), `E`/`W` (pycodestyle), `B` (flake8-bugbear), `S` (flake8-bandit), `C90` (mccabe), `SIM` (simplify), `PERF` (performance), `PL` (pylint), and many more. The `pyproject.toml` enables all relevant sets. For organisation-specific SonarQube rules, add custom Pylint checkers.

### Note on taint analysis

For deep data-flow taint tracking beyond what Bandit/Ruff's `S` rules offer, use [Pyre with Pysa](https://pyre-check.org/docs/pysa-basics/). Pysa is Facebook's static taint analysis tool that traces data flows from sources (e.g. user input) to sinks (e.g. `exec`, `subprocess`). Install separately with `pip install pyre-check`.

## License

MIT
