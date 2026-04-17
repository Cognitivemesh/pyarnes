# Quick Start

## Create a tool

```python
from dataclasses import dataclass
from typing import Any

from pyarnes.types import ToolHandler


@dataclass
class EchoTool(ToolHandler):
    """Tool that echoes its text argument."""

    async def execute(self, arguments: dict[str, Any]) -> Any:
        return arguments.get("text", "echo")
```

## Run the agent loop

```python
import asyncio

from pyarnes.harness.loop import AgentLoop, LoopConfig

loop = AgentLoop(
    tools={"echo": EchoTool()},
    model=your_model_client,
    config=LoopConfig(max_iterations=10),
)
messages = asyncio.run(loop.run([]))
```

## Add guardrails

```python
from pyarnes.harness.guardrails import GuardrailChain, PathGuardrail, CommandGuardrail

chain = GuardrailChain(guardrails=[
    PathGuardrail(allowed_roots=("/workspace",)),
    CommandGuardrail(),
])
chain.check("shell", {"command": "ls -la", "path": "/workspace/src"})
```
