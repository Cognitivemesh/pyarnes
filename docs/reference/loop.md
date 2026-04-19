---
persona: both
level: L2
tags: [reference, loop]
---

# Agent Loop

**Module:** `pyarnes_harness.loop`

The `AgentLoop` is the core runtime. It repeatedly asks the model for the next action, dispatches tool calls, handles errors, and accumulates messages until the model says it's done.

## LoopConfig

Tunables for the loop:

| Field | Type | Default | Description |
|---|---|---|---|
| `max_iterations` | `int` | `50` | Hard ceiling on loop cycles before forced stop |
| `max_retries` | `int` | `2` | Cap on transient-error retries per tool call |
| `retry_base_delay` | `float` | `1.0` | Seconds before the first retry (doubles each attempt) |

Validation: `max_iterations >= 1`, `max_retries >= 0`.

## AgentLoop

| Field | Type | Description |
|---|---|---|
| `tools` | `dict[str, ToolHandler]` | Mapping of tool names → handlers |
| `model` | `ModelClient` | The LLM client |
| `config` | `LoopConfig` | Loop tunables |
| `tool_call_logger` | `ToolCallLogger \| None` | Optional JSONL file logger |

### `async run(messages) -> list[dict]`

Runs the loop until the model returns a `final_answer` or `max_iterations` is reached.

**Error routing:**

1. `TransientError` → retry with backoff → if exhausted, return `ToolMessage(is_error=True)`
2. `LLMRecoverableError` → return `ToolMessage(is_error=True)` immediately
3. `UserFixableError` → re-raise to caller
4. Any other exception → wrap in `UnexpectedError` and re-raise

## ToolMessage

Fed back to the model after a tool call:

| Field | Type | Description |
|---|---|---|
| `tool_call_id` | `str` | Links to the original tool call |
| `content` | `str` | Tool output or error description |
| `is_error` | `bool` | `True` when the content describes a failure |
