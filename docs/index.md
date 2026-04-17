# pyarnes

> A minimal agentic harness engineering template for Python.

**pyarnes** adds verification loops, safety enforcement, and lifecycle management that AI coding tools miss. It captures raw outputs and errors, feeds that reality back to the model, applies guardrails around what the system can touch, and makes every step visible and debuggable.

## What problem does it solve?

AI coding agents (Claude Code, Cursor, Codex) generate tool calls but have no built-in system for:

- **Retrying flaky operations** — network timeouts, rate limits
- **Feeding errors back** — so the model can self-correct instead of crashing
- **Enforcing safety limits** — blocking `rm -rf /` or access outside `/workspace`
- **Tracking session state** — knowing if the agent is running, paused, or done
- **Logging everything** — structured JSONL that humans and machines can parse

pyarnes solves all of these with a single `AgentLoop` + guardrails + lifecycle FSM.

## Key features

| Feature | What it does |
|---|---|
| **Error taxonomy** | Routes failures through 4 types: retry, feedback, interrupt, or bubble up |
| **Agent loop** | Async loop that dispatches LLM tool calls with full error handling |
| **Guardrails** | Composable checks: path allowlists, command blocklists, tool allowlists |
| **Lifecycle FSM** | INIT → RUNNING → PAUSED → COMPLETED / FAILED with history |
| **JSONL logging** | Every event logged as structured JSON to stderr via loguru |
| **OpenAPI** | REST API for managing sessions, checking guardrails, and running evals |
| **Eval framework** | Score agent outputs with pluggable scorers (exact match, custom) |

## Quick start

```bash
uv sync                  # install everything
uv run tasks check       # lint + typecheck + test
uv run tasks watch       # TDD watch mode
uv run tasks help        # see all tasks
```

## Packages

| Package | Description |
|---|---|
| [`pyarnes-core`](packages/core.md) | Types, errors, lifecycle, JSONL logging |
| [`pyarnes-harness`](packages/harness.md) | Agent loop, tool registry, output capture |
| [`pyarnes-guardrails`](packages/guardrails.md) | Composable safety guardrails |
| [`pyarnes-bench`](packages/bench.md) | Evaluation and benchmarking toolkit |
| [`pyarnes-api`](packages/api.md) | OpenAPI REST interface (FastAPI) |

