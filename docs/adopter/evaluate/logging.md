---
persona: adopter
level: L2
tags: [adopter, evaluate, logging]
---

# Logging

**Module:** `pyarnes_core.observe.logger`

All pyarnes components log through a single structured logging layer. Every event is:

1. **Structured** — key-value pairs, not free-form strings
2. **JSONL-serialised** — one JSON object per line, easy for agents to parse
3. **On stderr** — stdout is reserved for tool results

## Where logs go

By default, all logs go to **stderr** as JSONL. This keeps stdout clean for tool output that gets fed back to the LLM.

```text
stderr ← JSONL log lines (structured events)
stdout ← tool results only
```

## Configuration

Call `configure_logging()` once at application startup:

```python
from pyarnes_core.observe.logger import configure_logging, get_logger

# JSONL mode (default) — for CI, production, agent parsing
configure_logging(level="INFO", json=True)

# Console mode — coloured, human-readable (for local development)
configure_logging(level="DEBUG", json=False)

# Custom stream
import io
buf = io.StringIO()
configure_logging(level="DEBUG", json=True, stream=buf)
```

## Getting a logger

```python
from pyarnes_core.observe.logger import get_logger

logger = get_logger(__name__)
logger.info("tool.success tool={tool} result={result}", tool="echo", result="hi")
```

The logger is a bound [loguru](https://loguru.readthedocs.io/) logger with the module name attached.

## Log format

### JSONL mode (default)

Each line is a JSON object:

```json
{"timestamp": "2026-04-17T15:00:00.123456+00:00", "level": "info", "event": "tool.success tool=echo result=hi", "logger_name": "pyarnes_harness.loop"}
```

### Console mode

```text
INFO     | pyarnes_harness.loop - tool.success tool=echo result=hi
```

## What gets logged

| Component | Events logged |
|---|---|
| **AgentLoop** | `loop.iteration`, `loop.completed`, `loop.max_iterations_reached` |
| **Tool dispatch** | `tool.success`, `tool.transient_retry`, `tool.transient_exhausted`, `tool.llm_recoverable` |
| **Lifecycle** | `lifecycle.transition from=X to=Y` |
| **OutputCapture** | `capture.success`, `capture.failure` |
| **ToolRegistry** | `registry.registered`, `registry.unregistered` |
| **Guardrails** | `guardrail.path_blocked`, `guardrail.command_blocked`, `guardrail.tool_not_allowed` |

## LogFormat enum

```python
from pyarnes_core.observe.logger import LogFormat

configure_logging(fmt=LogFormat.JSON)     # JSONL
configure_logging(fmt=LogFormat.CONSOLE)  # human-readable
```
