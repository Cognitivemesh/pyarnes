# pyarnes-harness

Runtime engine for the pyarnes agentic harness — agent loop, guardrails, tool registry, and capture.

## What's included

- **loop** — `AgentLoop` with structured error routing and retry logic
- **guardrails** — composable safety checks (path, command, tool-allowlist)
- **tools** — `ToolRegistry` for handler discovery and validation
- **capture** — `OutputCapture` and `ToolCallLogger` for full observability
