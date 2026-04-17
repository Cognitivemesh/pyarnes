# pyarnes

> A minimal agentic harness engineering template for Python.

**pyarnes** adds verification loops, safety enforcement, and lifecycle management that AI coding tools miss. It captures raw outputs and errors, feeds that reality back to the model, applies guardrails around what the system can touch, and makes every step visible and debuggable.

## Features

- **Four error types** — transient (retry), LLM-recoverable (feedback), user-fixable (interrupt), unexpected (bubble up)
- **Async-first** — built on `asyncio` for maximum performance
- **JSONL observability** — structured logging via `loguru`
- **Safety guardrails** — composable path, command, and tool-allowlist checks
- **Lifecycle FSM** — INIT → RUNNING → PAUSED → COMPLETED / FAILED
- **Monorepo** — `pyarnes-core` + `pyarnes-harness` workspace packages
- **Cross-platform task runner** — replaces Make with `uv run tasks <name>`

## Quick start

```bash
uv sync
uv run tasks check   # lint + typecheck + test
uv run tasks watch   # TDD watch mode
uv run tasks help    # see all tasks
```

## Monorepo structure

| Package | Description |
|---|---|
| `pyarnes-core` | Types, errors, lifecycle, logging |
| `pyarnes-harness` | Agent loop, guardrails, tools, capture |
| `pyarnes` | Root package (re-exports + CLI task runner) |
