# Errors

**Module:** `pyarnes_core.errors`

## HarnessError (base class)

All harness errors inherit from `HarnessError`, a frozen dataclass that is also an `Exception`.

| Field | Type | Default | Description |
|---|---|---|---|
| `message` | `str` | *(required)* | Human-readable error description |
| `context` | `dict[str, Any]` | `{}` | Arbitrary metadata |
| `severity` | `Severity` | `MEDIUM` | LOW, MEDIUM, HIGH, or CRITICAL |

## TransientError

Retriable failures (network timeout, rate limit). The agent loop retries with exponential backoff.

| Field | Type | Default |
|---|---|---|
| `max_retries` | `int` | `2` |
| `retry_delay_seconds` | `float` | `1.0` |

```python
raise TransientError(message="API timeout", max_retries=3, retry_delay_seconds=2.0)
```

## LLMRecoverableError

Errors the model can recover from. Converted into `ToolMessage(is_error=True)` and fed back.

| Field | Type | Default |
|---|---|---|
| `tool_call_id` | `str \| None` | `None` |

## UserFixableError

Requires human intervention. The loop raises this to the caller.

| Field | Type | Default |
|---|---|---|
| `prompt_hint` | `str` | `""` |

## UnexpectedError

Catch-all for bugs and unknown failures. Wraps the original exception.

| Field | Type | Default |
|---|---|---|
| `original` | `BaseException \| None` | `None` |
| `severity` | `Severity` | `CRITICAL` |

## Severity enum

`LOW`, `MEDIUM`, `HIGH`, `CRITICAL` — used to classify impact.

