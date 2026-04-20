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
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyarnes_core.types import ToolHandler


@dataclass
class ReadFileTool(ToolHandler):
    """Read a file from the workspace."""

    async def execute(self, arguments: dict[str, Any]) -> Any:
        path = arguments["path"]
        return await asyncio.to_thread(Path(path).read_text)
```

The `async` keyword means the function can pause while waiting for slow things (like network or file I/O). File I/O is blocking — we wrap `read_text` in `asyncio.to_thread` so it runs on a worker thread and does not stall the loop, per the async-first principle in [concepts.md](../evaluate/concepts.md). You do not need to understand asyncio internals.

## 2. Create a model client

The model client connects to your LLM. It returns either a tool call or a final answer:

```python
from pyarnes_core.types import ModelClient


@dataclass
class MyModel(ModelClient):
    async def next_action(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        # Call your LLM here and return either:
        # {"type": "tool_call", "tool": "read_file", "id": "call_1", "arguments": {"path": "a.py"}}
        # {"type": "final_answer", "content": "Here's the answer..."}
        ...
```

### Worked example — Anthropic SDK

The provider speaks its own tool-use shape; `next_action` is where you translate. Below is a minimal `ModelClient` that wraps the `anthropic` SDK and emits pyarnes's contract:

```python
from dataclasses import field

from anthropic import AsyncAnthropic
from pyarnes_core.types import ModelClient

TOOL_SCHEMAS = [
    {
        "name": "read_file",
        "description": "Read a file from the workspace.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
]


@dataclass
class AnthropicModel(ModelClient):
    """Thin adapter — Anthropic tool-use responses → pyarnes action dicts."""

    client: AsyncAnthropic = field(default_factory=AsyncAnthropic)
    model: str = "claude-sonnet-4-6"

    async def next_action(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )
        for block in response.content:
            if block.type == "tool_use":
                return {
                    "type": "tool_call",
                    "tool": block.name,
                    "id": block.id,
                    "arguments": block.input,
                }
        text = "".join(b.text for b in response.content if b.type == "text")
        return {"type": "final_answer", "content": text}
```

Two shape rules:

- Anthropic's `tool_use` block → `{"type": "tool_call", "tool": ..., "id": block.id, "arguments": block.input}`. The `id` threads back to `ToolMessage.tool_call_id` so the model can correlate the result.
- Any `text` content in the final turn → `{"type": "final_answer", "content": text}`. The loop returns as soon as it sees this type.

OpenAI's `tool_calls` shape is symmetric — map `choice.message.tool_calls[0].function.{name, arguments}` and the call `id` the same way; `arguments` arrives as a JSON string there, so `json.loads` it before returning.

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

## 5. Integrate guardrails into the loop

pyarnes **does not** auto-apply guardrails — that is a deliberate design choice (see [distribution.md § "What you still own"](../evaluate/distribution.md#what-you-still-own)). You compose them into your tools by wrapping each handler so that `chain.check(...)` runs before `handler.execute(...)`:

```python
from dataclasses import dataclass

from pyarnes_core.types import ToolHandler


@dataclass
class GuardedTool(ToolHandler):
    """Run a guardrail chain before delegating to the inner handler."""

    inner: ToolHandler
    chain: GuardrailChain
    tool_name: str

    async def execute(self, arguments: dict[str, Any]) -> Any:
        self.chain.check(self.tool_name, arguments)  # raises UserFixableError on violation
        return await self.inner.execute(arguments)


def register_guarded(
    registry: ToolRegistry,
    name: str,
    tool: ToolHandler,
    chain: GuardrailChain,
) -> None:
    """Register ``tool`` under ``name`` with the guardrail chain attached."""
    registry.register(name, GuardedTool(tool, chain, name))


register_guarded(registry, "read_file", ReadFileTool(), chain)
```

The helper keeps the tool name in one place — the registry key doubles as the guardrail-check identifier, so the two can never drift apart. A `UserFixableError` from `chain.check` escapes the loop so a human can approve or reject the call — see the [error taxonomy](../evaluate/errors.md).

## 6. Enable JSONL tool-call logging

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
