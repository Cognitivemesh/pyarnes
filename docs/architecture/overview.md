# Architecture Overview

pyarnes is structured as a monorepo with two workspace packages:

```text
pyarnes/
├── packages/
│   ├── core/         → pyarnes-core (types, errors, lifecycle, logging)
│   └── harness/      → pyarnes-harness (loop, guardrails, tools, capture)
├── src/pyarnes/      → root package (re-exports + CLI task runner)
└── tests/
    ├── unit/
    └── features/     → BDD / Gherkin
```

## Dependency graph

```text
pyarnes (root)
  ├── pyarnes-core    (no runtime deps except loguru)
  └── pyarnes-harness (depends on pyarnes-core + functional libs)
```

## Design principles

1. **Async-first** — all tool execution is async to avoid GIL contention.
2. **Structured logging** — every event is JSONL on stderr; stdout is reserved for tool results.
3. **Error taxonomy** — four error types route failures to the right handler.
4. **Composable guardrails** — stack safety checks via `GuardrailChain`.
5. **Lifecycle FSM** — every session has a trackable state machine.
