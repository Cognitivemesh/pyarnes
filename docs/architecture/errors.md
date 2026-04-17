# Error Taxonomy

## The problem

When an LLM-driven agent calls tools, failures happen constantly: network timeouts, malformed JSON, missing permissions, unexpected crashes. Treating all of them the same way (crash the loop) wastes work and frustrates users.

## The solution: four error types

pyarnes classifies every failure into exactly one of four categories. Each has a specific recovery strategy:

| Error | When to use | What happens |
|---|---|---|
| `TransientError` | Network timeout, rate limit, flaky API | Retry with exponential backoff (max 2 attempts) |
| `LLMRecoverableError` | Bad JSON schema, invalid tool args, semantic mistake | Feed the error back as a `ToolMessage(is_error=True)` so the model adjusts |
| `UserFixableError` | Missing API key, needs approval, permission denied | Interrupt the loop and surface to a human |
| `UnexpectedError` | Bug in tool code, assertion failure, unknown crash | Bubble up immediately for debugging |

## Hierarchy

All errors inherit from `HarnessError`, which is a frozen dataclass:

```python
from pyarnes_core.errors import HarnessError, Severity

err = HarnessError(
    message="Something went wrong",
    context={"tool": "read_file", "path": "/etc/passwd"},
    severity=Severity.HIGH,
)
```

Fields: `message` (str), `context` (dict), `severity` (LOW / MEDIUM / HIGH / CRITICAL).

## How the agent loop routes errors

```text
Tool raises exception
  │
  ├─ TransientError     → retry (up to 2×) → ToolMessage(is_error=True)
  ├─ LLMRecoverableError → ToolMessage(is_error=True) → model self-corrects
  ├─ UserFixableError    → raise to caller → human intervenes
  └─ anything else       → wrap in UnexpectedError → raise to caller
```

## Examples

```python
from pyarnes_core.errors import TransientError, LLMRecoverableError, UserFixableError

# In a tool handler:
raise TransientError(message="API timeout", max_retries=3, retry_delay_seconds=2.0)

raise LLMRecoverableError(message="Expected JSON but got plain text", tool_call_id="call_abc")

raise UserFixableError(message="Missing OPENAI_API_KEY", prompt_hint="Set the OPENAI_API_KEY environment variable")
```

