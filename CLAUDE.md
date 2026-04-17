# Pyarnes — Project Instructions

## What is this?

A minimal agentic harness engineering template. It does **not** replace Claude Code, Cursor, or Codex — it **collaborates** with them by adding verification loops, safety enforcement, and lifecycle management that these tools lack.

## Quick commands

```bash
uv run tasks help        # list all tasks
uv run tasks test        # run tests
uv run tasks check       # lint + typecheck + test
uv run tasks watch       # TDD watch mode
uv run tasks format      # auto-format
uv run tasks lint        # ruff lint
uv run tasks security    # bandit security scan
uv run tasks radon:cc    # cyclomatic complexity
uv run tasks vulture     # dead code detection
uv run tasks complexity  # radon:cc + radon:mi
uv run tasks docs:serve  # local docs site
```

## Error taxonomy

| Type | Behaviour |
|---|---|
| `TransientError` | Retry with exponential backoff (cap: 2) |
| `LLMRecoverableError` | Return as ToolMessage so the model adjusts |
| `UserFixableError` | Interrupt for human input |
| `UnexpectedError` | Bubble up for debugging |

## Key architecture (monorepo)

- `packages/core/` — **pyarnes-core**: types, errors, lifecycle, observe/logging
- `packages/harness/` — **pyarnes-harness**: loop, tools, capture
- `packages/guardrails/` — **pyarnes-guardrails**: composable safety guardrails
- `packages/bench/` — **pyarnes-bench**: evaluation and benchmarking toolkit
- `packages/api/` — **pyarnes-api**: OpenAPI REST interface (FastAPI)
- `src/pyarnes/` — root package (CLI task runner only)
- `tests/unit/` — unit tests
- `tests/features/` — BDD feature files (pytest-bdd / Gherkin)
- `docs/` — MkDocs Material documentation source

## Conventions

- All code is **async-first** (asyncio) to avoid GIL contention.
- Logging goes to **stderr** as JSONL via **loguru**; stdout is reserved for tool results.
- Docstrings follow **PEP 257** conventions (Google style).
- Use `uv run tasks tdd` workflow: Red → Green → Refactor.
- Types are enforced via `ruff` + `ty`.
