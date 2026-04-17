# Quick Start

This guide walks you through creating a tool, running the agent loop, and adding guardrails.

## 1. Create a tool handler

Every tool implements the `ToolHandler` ABC from `pyarnes_core.types`:

```python
from dataclasses import dataclass
from typing import Any

from pyarnes_core.types import ToolHandler


@dataclass
class ReadFileTool(ToolHandler):
    """Read a file from the workspace."""

    async def execute(self, arguments: dict[str, Any]) -> Any:
        path = arguments["path"]
        return open(path).read()
```

## 2. Create a model client

The model client connects to your LLM. It returns either a tool call or a final answer:

```python
@dataclass
class MyModel(ModelClient):
    async def next_action(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        # Call your LLM here and return either:
        # {"type": "tool_call", "tool": "read_file", "id": "call_1", "arguments": {"path": "a.py"}}
        # {"type": "final_answer", "content": "Here's the answer..."}
        ...
```

## 3. Run the agent loop

```python
import asyncio

from pyarnes_harness.loop import AgentLoop, LoopConfig
from pyarnes_harness.tools.registry import ToolRegistry

registry = ToolRegistry()
registry.register("read_file", ReadFileTool())

loop = AgentLoop(
    tools=registry.as_dict(),
    model=MyModel(),
    config=LoopConfig(max_iterations=10, max_retries=2),
)
messages = asyncio.run(loop.run([{"role": "user", "content": "Read main.py"}]))
```

## 4. Add guardrails

Guardrails validate tool calls before execution:

```python
from pyarnes_guardrails import GuardrailChain, PathGuardrail, CommandGuardrail

chain = GuardrailChain(guardrails=[
    PathGuardrail(allowed_roots=("/workspace",)),
    CommandGuardrail(),  # blocks rm -rf /, sudo, chmod 777, curl|sh
])

# Passes silently:
chain.check("read_file", {"path": "/workspace/src/main.py"})

# Raises UserFixableError:
chain.check("read_file", {"path": "/etc/passwd"})
```

## 5. Enable JSONL tool-call logging

Log every tool invocation to disk:

```python
from pathlib import Path
from pyarnes_harness.capture.tool_log import ToolCallLogger

with ToolCallLogger(path=Path(".harness/tool_calls.jsonl")) as logger:
    loop = AgentLoop(
        tools=registry.as_dict(),
        model=MyModel(),
        tool_call_logger=logger,
    )
    asyncio.run(loop.run([]))
```

Each line in the JSONL file looks like:

```json
{"tool": "read_file", "arguments": {"path": "a.py"}, "result": "...", "is_error": false, "started_at": "2026-04-17T15:00:00+00:00", "finished_at": "2026-04-17T15:00:01+00:00", "duration_seconds": 0.42}
```

## 6. Use the REST API

Start the API server and manage everything over HTTP:

```bash
uv run uvicorn pyarnes_api.app:app --reload
```

```bash
# Check guardrails
curl -X POST http://localhost:8000/api/v1/guardrails/check \
  -H "Content-Type: application/json" \
  -d '{"tool_name": "shell", "arguments": {"command": "ls -la"}}'

# Manage lifecycle
curl -X POST http://localhost:8000/api/v1/lifecycle/transition \
  -H "Content-Type: application/json" \
  -d '{"action": "start"}'

# Run evaluations
curl -X POST http://localhost:8000/api/v1/eval \
  -H "Content-Type: application/json" \
  -d '{"scenarios": [{"scenario": "test1", "expected": "hello", "actual": "hello"}]}'
```

