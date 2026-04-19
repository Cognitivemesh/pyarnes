---
persona: both
level: L2
tags: [reference, errors]
---

# Errors

**Module:** `pyarnes_core.errors`

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

## Routing through the agent loop

```mermaid
flowchart TD
    Tool[Tool raises exception]
    Tool --> Classify{Error type?}
    Classify -->|TransientError| Retry[Retry up to 2x<br/>with exponential backoff]
    Classify -->|LLMRecoverableError| Feedback[ToolMessage is_error=True<br/>model self-corrects]
    Classify -->|UserFixableError| Human[Raise to caller<br/>human intervenes]
    Classify -->|anything else| Bubble[Wrap in UnexpectedError<br/>raise to caller]
    Retry -->|exhausted| Feedback
```

## Hierarchy

All errors inherit from `HarnessError`, a frozen dataclass that is also an `Exception`.

```python
from pyarnes_core.errors import HarnessError, Severity

err = HarnessError(
    message="Something went wrong",
    context={"tool": "read_file", "path": "/etc/passwd"},
    severity=Severity.HIGH,
)
```

## Examples

```python
from pyarnes_core.errors import TransientError, LLMRecoverableError, UserFixableError

# In a tool handler:
raise TransientError(message="API timeout", max_retries=3, retry_delay_seconds=2.0)

raise LLMRecoverableError(message="Expected JSON but got plain text", tool_call_id="call_abc")

raise UserFixableError(message="Missing OPENAI_API_KEY", prompt_hint="Set the OPENAI_API_KEY environment variable")
```

## Field reference

### HarnessError (base class)

| Field | Type | Default | Description |
|---|---|---|---|
| `message` | `str` | *(required)* | Human-readable error description |
| `context` | `dict[str, Any]` | `{}` | Arbitrary metadata |
| `severity` | `Severity` | `MEDIUM` | LOW, MEDIUM, HIGH, or CRITICAL |

### TransientError

Retriable failures (network timeout, rate limit). The agent loop retries with exponential backoff.

| Field | Type | Default |
|---|---|---|
| `max_retries` | `int` | `2` |
| `retry_delay_seconds` | `float` | `1.0` |

### LLMRecoverableError

Errors the model can recover from. Converted into `ToolMessage(is_error=True)` and fed back.

| Field | Type | Default |
|---|---|---|
| `tool_call_id` | `str \| None` | `None` |

### UserFixableError

Requires human intervention. The loop raises this to the caller.

| Field | Type | Default |
|---|---|---|
| `prompt_hint` | `str` | `""` |

### UnexpectedError

Catch-all for bugs and unknown failures. Wraps the original exception.

| Field | Type | Default |
|---|---|---|
| `original` | `BaseException \| None` | `None` |
| `severity` | `Severity` | `CRITICAL` |

### Severity enum

`LOW`, `MEDIUM`, `HIGH`, `CRITICAL` — used to classify impact.
