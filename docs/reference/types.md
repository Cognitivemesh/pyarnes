---
persona: both
level: L2
tags: [reference, core]
---

# Core Types

## ToolHandler

Abstract base class for every tool the harness can invoke. You subclass this and implement `execute()`.

**Module:** `pyarnes_core.types`

```python
from pyarnes_core.types import ToolHandler

class ReadFileTool(ToolHandler):
    async def execute(self, arguments: dict[str, Any]) -> Any:
        return open(arguments["path"]).read()
```

**Method:** `async execute(arguments: dict[str, Any]) -> Any`

- `arguments` — key-value arguments from the LLM's tool call
- Returns the tool's result (gets stringified for the model)

## ModelClient

Abstract base class for the backing LLM client. Controls what the agent does next.

```python
from pyarnes_core.types import ModelClient

class MyModel(ModelClient):
    async def next_action(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        # Return one of:
        # {"type": "tool_call", "tool": "name", "id": "call_1", "arguments": {...}}
        # {"type": "final_answer", "content": "..."}
        ...
```

**Method:** `async next_action(messages: list[dict[str, Any]]) -> dict[str, Any]`

- `messages` — full conversation history so far
- Returns a dict describing either a tool call or a final answer
