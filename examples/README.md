# Examples: with and without pyarnes

Both examples implement the same file-summarisation agent.  The agent reads a
directory, optionally reads some files, and writes a 2-3 sentence summary.

## without-pyarnes

Raw loop using the Anthropic SDK directly.  Error handling, retry logic, and
lifecycle transitions are all inline.

```
python examples/without-pyarnes/agent.py <directory>
```

| Metric | Value |
|---|---|
| Lines of code | ~120 |
| Error handling lines | ~20 (scattered inline) |
| Retry logic | hardcoded 3-attempt loop |
| Lifecycle management | none |
| Guardrails | none |
| Structured logging | none |
| Tests | none (no injection points) |

## with-pyarnes

Same scenario wired through `AgentRuntime`.  The framework owns error routing,
retry policy, lifecycle transitions, and structured JSONL logging.

```
uv run python examples/with-pyarnes/agent.py <directory>
```

| Metric | Value |
|---|---|
| Lines of code | ~80 (tools + adapter) |
| Error handling lines | 2 (`UserFixableError` raises) |
| Retry policy | config-driven, per-error overridable |
| Lifecycle management | INIT → RUNNING → COMPLETED/FAILED |
| Guardrails | PathGuardrail + CommandGuardrail |
| Structured logging | JSONL to stderr via loguru |
| Tests | injectable (mock `ModelClient`, `ToolHandler`) |

## Key differences

1. **Error taxonomy** — instead of bare `except Exception`, the harness routes
   errors by type: transient → retry, LLM-recoverable → feed back to model,
   user-fixable → interrupt, unexpected → crash with traceback.

2. **Guardrails** — `PathGuardrail` blocks `read_file` from escaping the target
   directory; `CommandGuardrail` blocks shell injection attempts.  Without the
   harness you'd have to add these checks manually to every tool.

3. **Testability** — `AgentRuntime` accepts any `ModelClient` and `ToolHandler`
   implementation, so unit tests inject stubs without patching global state.
