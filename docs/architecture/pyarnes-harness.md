# pyarnes-harness

The runtime engine that drives agent execution.

## What it provides

| Module | Key classes | Purpose |
|---|---|---|
| `pyarnes_harness.loop` | `AgentLoop`, `LoopConfig`, `ToolMessage` | Core async agent loop with structured error handling |
| `pyarnes_harness.tools.registry` | `ToolRegistry` | Named handler discovery and validation |
| `pyarnes_harness.capture.output` | `CapturedOutput`, `OutputCapture` | Record tool stdout, stderr, return values, and errors |
| `pyarnes_harness.capture.tool_log` | `ToolCallEntry`, `ToolCallLogger` | JSONL file logger for tool invocations |
| `pyarnes_harness.guardrails` | Re-exports from `pyarnes-guardrails` | Backwards compatibility |

## How the loop works

1. Ask the model for the next action
2. If `final_answer` → stop and return messages
3. If `tool_call` → dispatch to the handler
4. Handle errors according to the taxonomy (retry, feedback, interrupt, or crash)
5. Append the tool result to messages and go back to step 1
6. If `max_iterations` reached → stop and return messages

## Dependencies

- `pyarnes-core` — error types, lifecycle, logging
- `pyarnes-guardrails` — safety guardrails (re-exported for convenience)
- `returns`, `toolz`, `more-itertools`, `funcy` — functional programming utilities

