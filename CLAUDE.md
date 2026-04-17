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
```

## Error taxonomy

| Type | Behaviour |
|---|---|
| `TransientError` | Retry with exponential backoff (cap: 2) |
| `LLMRecoverableError` | Return as ToolMessage so the model adjusts |
| `UserFixableError` | Interrupt for human input |
| `UnexpectedError` | Bubble up for debugging |

## Key architecture

- `src/pyarnes/harness/` — agent loop, errors, guardrails, lifecycle
- `src/pyarnes/capture/` — raw output & error recording
- `src/pyarnes/observe/` — JSONL structured logging (structlog)
- `src/pyarnes/tools/` — tool registry
- `src/pyarnes/tasks/` — cross-platform task runner (replaces Make)
- `tests/unit/` — unit tests
- `tests/features/` — BDD feature files (pytest-bdd / Gherkin)

## Conventions

- All code is **async-first** (asyncio) to avoid GIL contention.
- Logging goes to **stderr** as JSONL; stdout is reserved for tool results.
- Use `uv run tasks tdd` workflow: Red → Green → Refactor.
- Types are enforced via `ruff` + `ty`.
