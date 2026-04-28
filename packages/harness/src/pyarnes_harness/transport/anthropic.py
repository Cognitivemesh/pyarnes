"""Anthropic native SDK transport adapter.

``import anthropic`` is deferred inside ``complete()`` so that
pyarnes-harness does not force the Anthropic SDK as a hard dependency.
"""

from __future__ import annotations

import json
from typing import Any

from pyarnes_harness.transport.ports import NormalizedResponse, NormalizedToolCall, ProviderTransport


class AnthropicTransport(ProviderTransport):
    """Route completions through the Anthropic Python SDK.

    Args:
        model: Anthropic model ID, e.g. ``"claude-sonnet-4-6"``.
        **anthropic_kwargs: Extra kwargs forwarded to ``client.messages.create()``.
    """

    def __init__(self, model: str, **anthropic_kwargs: Any) -> None:
        """Store model name and any extra litellm kwargs."""
        self.model = model
        self._kwargs = anthropic_kwargs

    async def complete(  # noqa: D102
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        **kwargs: Any,
    ) -> NormalizedResponse:
        import anthropic  # noqa: PLC0415 — deferred to avoid hard dependency

        client = anthropic.AsyncAnthropic()

        tool_defs = [
            {
                "name": t["name"],
                "description": t.get("description", ""),
                "input_schema": t.get("parameters", {"type": "object", "properties": {}}),
            }
            for t in tools
        ]

        # Anthropic separates system from human/assistant messages
        system_msgs = [m["content"] for m in messages if m.get("role") == "system"]
        conv_msgs = [m for m in messages if m.get("role") != "system"]

        create_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": conv_msgs,
            "max_tokens": self._kwargs.pop("max_tokens", 4096),
            **{**self._kwargs, **kwargs},
        }
        if system_msgs:
            create_kwargs["system"] = "\n".join(system_msgs)
        if tool_defs:
            create_kwargs["tools"] = tool_defs

        response = await client.messages.create(**create_kwargs)

        finish_reason = "stop"
        if response.stop_reason == "tool_use":
            finish_reason = "tool_calls"
        elif response.stop_reason == "max_tokens":
            finish_reason = "length"

        content_text = ""
        tool_calls: list[NormalizedToolCall] = []

        for block in response.content:
            if block.type == "text":
                content_text += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    NormalizedToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=json.dumps(block.input),
                    )
                )

        usage = None
        if response.usage:
            usage = {
                "input": response.usage.input_tokens,
                "output": response.usage.output_tokens,
            }

        return NormalizedResponse(
            content=content_text,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
        )
