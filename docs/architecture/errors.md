# Error Taxonomy

pyarnes routes tool failures through four canonical error types:

| Error | Behaviour |
|---|---|
| `TransientError` | Retry with exponential backoff (cap: 2) |
| `LLMRecoverableError` | Return as ToolMessage so the model adjusts |
| `UserFixableError` | Interrupt for human input |
| `UnexpectedError` | Bubble up for debugging |

All errors inherit from `HarnessError` which is a frozen dataclass with `message`, `context`, and `severity` fields.

## Flow diagram

```text
Tool raises exception
  │
  ├─ TransientError    → retry (max 2) → ToolMessage(is_error=True)
  ├─ LLMRecoverableError → ToolMessage(is_error=True) → model retries
  ├─ UserFixableError  → raise to caller → human intervenes
  └─ UnexpectedError   → raise to caller → debug / postmortem
```
