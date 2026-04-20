---
persona: adopter
level: L3
tags: [adopter, build, production, deployment]
---

# Running in production

This page covers the additional steps needed when moving a pyarnes-based agent
from a developer laptop to a production environment.

## Configuration checklist

Before deploying, verify each of these:

- [ ] `LoopConfig.max_iterations` is set to a value appropriate for your
      worst-case task (default is 10 — raise for long-running agents, lower
      for latency-sensitive ones).
- [ ] `LoopConfig.max_retries` is 2 or fewer. More retries mean more model
      calls on failure; cap it at what your SLA allows.
- [ ] `PathGuardrail` has `allowed_roots` scoped to your actual workspace
      directory, not `/` or the home directory.
- [ ] `CommandGuardrail` is wired to every tool that accepts shell commands.
- [ ] `ToolAllowlistGuardrail` lists only the tools the agent should call.
- [ ] Logging is configured with `configure_logging(level="INFO", json=True)`
      so structured JSONL lands in your log aggregator.
- [ ] `ToolCallLogger` writes to a persistent path (not `/tmp`).

## Structuring the agent entry point

```python
import asyncio
from pathlib import Path

from pyarnes_core.observe.logger import configure_logging
from pyarnes_guardrails import CommandGuardrail, GuardrailChain, PathGuardrail
from pyarnes_harness.capture.tool_log import ToolCallLogger
from pyarnes_harness.loop import AgentLoop, LoopConfig
from pyarnes_harness.tools.registry import ToolRegistry

from myagent.model import MyModel
from myagent.tools import ReadFileTool, WriteFileTool

configure_logging(level="INFO", json=True)

registry = ToolRegistry()
chain = GuardrailChain(guardrails=[
    PathGuardrail(allowed_roots=("/workspace",)),
    CommandGuardrail(),
])

registry.register("read_file", ReadFileTool())
registry.register("write_file", WriteFileTool())

log_path = Path("/var/log/myagent/tool_calls.jsonl")
log_path.parent.mkdir(parents=True, exist_ok=True)

async def run(user_message: str) -> list[dict]:
    with ToolCallLogger(path=log_path) as logger:
        loop = AgentLoop(
            tools=registry.as_dict(),
            model=MyModel(),
            config=LoopConfig(max_iterations=20, max_retries=2),
            tool_call_logger=logger,
        )
        return await loop.run([{"role": "user", "content": user_message}])

if __name__ == "__main__":
    import sys
    result = asyncio.run(run(sys.argv[1]))
    print(result[-1]["content"])
```

## Error handling at the boundary

The four error types behave differently at the process boundary:

| Error | Default harness behaviour | What to do in production |
|---|---|---|
| `TransientError` | Retry up to `max_retries` | Log after final retry; emit a metric |
| `LLMRecoverableError` | Return as `ToolMessage` | Log if the model keeps triggering the same error |
| `UserFixableError` | Bubble up (loop stops) | Surface to UI or alert queue; do not auto-retry |
| `UnexpectedError` | Bubble up (loop stops) | Page on-call; attach `original` exception |

Wrap your entry point to handle `UserFixableError` and `UnexpectedError`
distinctly:

```python
from pyarnes_core.errors import UnexpectedError, UserFixableError

try:
    result = asyncio.run(run(message))
except UserFixableError as e:
    # Surface to the user who triggered the run
    send_user_notification(str(e))
except UnexpectedError as e:
    # Page on-call
    alert_oncall(str(e), original=e.original)
    raise
```

## Observability

Every tool call is logged by `ToolCallLogger`. Ingest the JSONL into your
preferred log stack:

```bash
# Tail live tool calls
tail -f /var/log/myagent/tool_calls.jsonl | jq .

# Count errors in the last hour
jq 'select(.is_error == true)' /var/log/myagent/tool_calls.jsonl | wc -l
```

Key fields: `tool`, `arguments`, `result`, `is_error`, `duration_seconds`,
`started_at`, `finished_at`.

## Sizing guidance

| Dimension | Starting point | Adjust when |
|---|---|---|
| `max_iterations` | 10 | Tasks require long chains of tool calls |
| `max_retries` | 2 | Upstream model has higher transient error rate |
| Worker processes | 1 per CPU | CPU-bound post-processing in tools |
| JSONL log rotation | 100 MB | High-volume production traffic |

## See also

- [Quick start](quickstart.md) — build and wire tools.
- [Error taxonomy](../evaluate/errors.md) — full error-type reference.
- [Security & threat model](../evaluate/security.md) — guardrail design.
- [Logging](../evaluate/logging.md) — JSONL log format reference.
