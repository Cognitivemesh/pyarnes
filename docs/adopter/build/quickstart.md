---
persona: adopter
level: L2
tags: [adopter, build, quickstart]
---

# Quick start

This guide walks you through creating a tool, running the agent loop, and adding guardrails.

## What you are about to build

```mermaid
sequenceDiagram
    participant User
    participant Loop as AgentLoop
    participant Guard as GuardrailChain
    participant Tool as ReadFileTool
    participant Model as MyModel

    User->>Loop: run([{role: user, content: Read main.py}])
    Loop->>Model: next_action(messages)
    Model-->>Loop: tool_call(read_file, {path: ...})
    Loop->>Guard: check(read_file, {path: ...})
    Guard-->>Loop: ok
    Loop->>Tool: execute({path: ...})
    Tool-->>Loop: file contents
    Loop->>Model: next_action(messages + tool_result)
    Model-->>Loop: final_answer
    Loop-->>User: messages
```

## 1. Create a tool handler

Every tool implements the `ToolHandler` ABC from `pyarnes_core.types`. *(`ABC` = "Abstract Base Class" — a Python pattern for "you must implement this method". You don't need to know how it works; just subclass it.)*

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

The `async` keyword means the function can pause while waiting for slow things (like network or file I/O). You do not need to understand asyncio internals.

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

## See also

- [Packages overview](packages.md) — what each `pyarnes-*` package provides.
- [pyarnes-harness deep dive](../../maintainer/packages/harness.md) (agent loop, capture) · [pyarnes-guardrails deep dive](../../maintainer/packages/guardrails.md).
