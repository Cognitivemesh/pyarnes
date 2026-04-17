# pyarnes-harness

Runtime engine for agent execution.

## Modules

| Module | Contents |
|---|---|
| `pyarnes_harness.loop` | `AgentLoop`, `LoopConfig`, `ToolMessage` |
| `pyarnes_harness.guardrails` | Re-exports from `pyarnes-guardrails` |
| `pyarnes_harness.tools.registry` | `ToolRegistry` |
| `pyarnes_harness.capture.output` | `CapturedOutput`, `OutputCapture` |
| `pyarnes_harness.capture.tool_log` | `ToolCallEntry`, `ToolCallLogger` |

## Dependencies

- `pyarnes-core` — core types and logging
- `pyarnes-guardrails` — safety guardrails
- `returns` — functional result types
- `toolz` — functional utilities
- `more-itertools` — extended itertools
- `funcy` — functional helpers
