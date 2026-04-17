# pyarnes-core

Core abstractions for the pyarnes agentic harness — types, errors, lifecycle, and logging.

## What's included

- **types** — `ToolHandler` and `ModelClient` abstract base classes
- **errors** — four-error taxonomy (transient, LLM-recoverable, user-fixable, unexpected)
- **lifecycle** — `Phase` / `Lifecycle` finite-state machine
- **observe** — structured JSONL logging via loguru
