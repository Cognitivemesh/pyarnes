"""LiteLLM provider transport adapter.

``import litellm`` is deferred inside ``complete()`` so that pyarnes-harness
does not force litellm as a hard install-time dependency.
"""

from __future__ import annotations

from typing import Any

from pyarnes_harness.transport.ports import NormalizedResponse, NormalizedToolCall, ProviderTransport


class LiteLLMTransport(ProviderTransport):
    """Route completions through `litellm <https://docs.litellm.ai>`_.

    Supports every litellm-covered provider (OpenAI, Anthropic, Cohere, etc.)
    with a single interface.

    Args:
        model: litellm model string, e.g. ``"openai/gpt-4o-mini"``.
        **litellm_kwargs: Extra kwargs forwarded to ``litellm.acompletion()``.
    """

    def __init__(self, model: str, **litellm_kwargs: Any) -> None:
        """Store model name and any extra litellm kwargs."""
        self.model = model
        self._kwargs = litellm_kwargs

    async def complete(  # noqa: D102
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        **kwargs: Any,
    ) -> NormalizedResponse:
        import litellm  # noqa: PLC0415 — deferred to avoid hard dependency

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

        response = await litellm.acompletion(
            model=self.model,
            messages=messages,
            tools=tool_defs or None,
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
                "input": response.usage.prompt_tokens or 0,
                "output": response.usage.completion_tokens or 0,
            }

        return NormalizedResponse(
            content=message.content or "",
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
        )
