---
persona: adopter
tags: [adopter, build, llm, anthropic]
---

# LLM integration (Anthropic SDK)

`ModelClient` is provider-agnostic. Your adapter only needs to map provider output into pyarnes actions:

- `{"type": "tool_call", ...}`
- `{"type": "final_answer", ...}`

```python
from dataclasses import dataclass, field
from typing import Any

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
    }
]


@dataclass
class AnthropicModel(ModelClient):
    """Anthropic tool-use blocks -> pyarnes action dicts."""

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

        text = "".join(block.text for block in response.content if block.type == "text")
        return {"type": "final_answer", "content": text}
```

`block.id` should be preserved as the tool call ID so tool results can be correlated through `ToolMessage.tool_call_id`.

OpenAI function-calling is symmetric: map function name + parsed arguments + call ID into the same `tool_call` shape, and map assistant text output to `final_answer`.
