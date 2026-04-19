# pyarnes-guardrails

Composable safety guardrails that validate tool calls before execution.

## What it provides

| Class | Purpose |
|---|---|
| `Guardrail` | Abstract base class — implement `check()` for custom guardrails |
| `PathGuardrail` | Block access to paths outside allowed roots |
| `CommandGuardrail` | Block dangerous shell commands (sudo, rm -rf /, etc.) |
| `ToolAllowlistGuardrail` | Only allow pre-approved tool names |
| `GuardrailChain` | Stack multiple guardrails — first violation stops the chain |

## How guardrails work

Every guardrail has a single method:

```python
def check(self, tool_name: str, arguments: dict[str, Any]) -> None:
```

- If the call is safe → returns `None`
- If the call is dangerous → raises `UserFixableError` with a message and prompt hint

## Dependencies

- `pyarnes-core` — `UserFixableError` error type and logging

