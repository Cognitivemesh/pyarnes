# pyarnes-harness

Runtime engine for agent execution.

## Modules

| Module | Contents |
|---|---|
| `pyarnes_harness.loop` | `AgentLoop`, `LoopConfig`, `ToolMessage` |
| `pyarnes_harness.guardrails` | `Guardrail` ABC, `PathGuardrail`, `CommandGuardrail`, `ToolAllowlistGuardrail`, `GuardrailChain` |
| `pyarnes_harness.tools.registry` | `ToolRegistry` |
| `pyarnes_harness.capture.output` | `CapturedOutput`, `OutputCapture` |
| `pyarnes_harness.capture.tool_log` | `ToolCallEntry`, `ToolCallLogger` |

## Dependencies

- `pyarnes-core` — core types and logging
- `returns` — functional result types
- `toolz` — functional utilities
- `more-itertools` — extended itertools
- `funcy` — functional helpers
