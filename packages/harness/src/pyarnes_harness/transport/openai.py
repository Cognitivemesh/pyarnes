"""OpenAI native SDK transport adapter.

``import openai`` is deferred inside ``complete()`` so that pyarnes-harness
does not force the OpenAI SDK as a hard dependency.
"""

from __future__ import annotations

from typing import Any

from pyarnes_harness.transport.ports import NormalizedResponse, NormalizedToolCall, ProviderTransport


class OpenAITransport(ProviderTransport):
    """Route completions through the OpenAI Python SDK.

    Args:
        model: OpenAI model ID, e.g. ``"gpt-4o-mini"``.
        **openai_kwargs: Extra kwargs forwarded to ``client.chat.completions.create()``.
    """

    def __init__(self, model: str, **openai_kwargs: Any) -> None:
        """Store model name and any extra openai kwargs."""
        self.model = model
        self._kwargs = openai_kwargs

    async def complete(  # noqa: D102
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        **kwargs: Any,
    ) -> NormalizedResponse:
        import openai  # noqa: PLC0415 — deferred to avoid hard dependency

        client = openai.AsyncOpenAI()

        tool_defs = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("parameters", {}),
                },
            }
            for t in tools
        ]

        response = await client.chat.completions.create(  # type: ignore
            model=self.model,
            messages=messages,
            tools=tool_defs or openai.NOT_GIVEN,
            **{**self._kwargs, **kwargs},
        )

        choice = response.choices[0]
        message = choice.message
        finish_reason = choice.finish_reason or "stop"

        tool_calls: list[NormalizedToolCall] = []
        if message.tool_calls:
            tool_calls = [
                NormalizedToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=tc.function.arguments or "{}",
                )
                for tc in message.tool_calls
            ]

        usage = None
        if response.usage:
            usage = {
                "input": response.usage.prompt_tokens,
                "output": response.usage.completion_tokens,
            }

        return NormalizedResponse(
            content=message.content or "",
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
        )
