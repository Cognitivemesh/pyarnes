# Architecture Overview

## Monorepo layout

pyarnes is a **uv workspace monorepo**. Each package has its own `pyproject.toml` and can be installed independently.

```text
pyarnes/
├── packages/
│   ├── core/         → pyarnes-core    (types, errors, lifecycle, logging)
│   ├── harness/      → pyarnes-harness (loop, tools, capture)
│   ├── guardrails/   → pyarnes-guardrails (safety checks)
│   ├── bench/        → pyarnes-bench   (evaluation framework)
│   └── api/          → pyarnes-api     (FastAPI REST interface)
├── src/pyarnes/      → root package    (CLI task runner only)
└── tests/
    ├── unit/         → unit tests for all packages
    └── features/     → BDD / Gherkin acceptance tests
```

## Dependency graph

```text
pyarnes-api
  ├── pyarnes-harness
  │     ├── pyarnes-core (loguru)
  │     └── pyarnes-guardrails
  │           └── pyarnes-core
  ├── pyarnes-bench
  │     └── pyarnes-core
  └── fastapi + uvicorn
```

`pyarnes-core` is the foundation — every other package depends on it for error types and logging.

## Design principles

1. **Async-first** — all tool execution uses `asyncio` to avoid GIL contention. The `AgentLoop` dispatches tool calls as async operations.

2. **Structured logging** — every event is emitted as JSONL on **stderr** via `loguru`. Stdout is reserved for tool results. See [Logging](../api/logging.md) for configuration.

3. **Error taxonomy** — four error types ensure failures are always routed correctly: retry, feed back, interrupt, or bubble up. See [Error Taxonomy](errors.md).

4. **Composable guardrails** — safety checks stack via `GuardrailChain`. Each guardrail is a simple `check(tool_name, arguments)` → raises `UserFixableError` or passes.

5. **Lifecycle FSM** — every session has a trackable state machine with full transition history. See [Lifecycle](lifecycle.md).

6. **No magic** — there are no decorators, metaclasses, or auto-discovery. You register tools explicitly in a `ToolRegistry`, wire up guardrails, and run the loop.

