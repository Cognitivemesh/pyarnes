"""Provider transport abstraction — normalized types and protocol.

All provider-specific adapters (LiteLLM, Anthropic, OpenAI) implement
``ProviderTransport`` and return ``NormalizedResponse`` objects so the rest
of the harness stays provider-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pyarnes_harness.repair import repair_json_args

if TYPE_CHECKING:
    from pyarnes_harness.tools.registry import ToolRegistry

__all__ = [
    "NormalizedResponse",
    "NormalizedToolCall",
    "ProviderTransport",
    "TransportModelClient",
]


@dataclass(frozen=True)
class NormalizedToolCall:
    """A single tool invocation returned by a provider, pre-normalized."""

    id: str
    name: str
    arguments: str  # JSON string; may need repair_json_args before dispatch


@dataclass(frozen=True)
class NormalizedResponse:
    """Provider-agnostic completion response."""

    content: str
    tool_calls: list[NormalizedToolCall]
    finish_reason: str  # "stop" | "tool_calls" | "length"
    usage: dict[str, int] | None = None


class ProviderTransport:
    """Protocol for provider transport adapters.

    Concrete implementations must override ``complete()``.  The class is kept
    as a plain base (not typing.Protocol) so runtime ``isinstance`` checks work
    without importing ``typing_extensions``.
    """

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        **kwargs: Any,
    ) -> NormalizedResponse:
        """Send *messages* to the provider and return a normalized response.

        Args:
            messages: Conversation history in provider-agnostic format.
            tools: List of tool definitions (converted by the adapter).
            **kwargs: Extra provider-specific options (temperature, etc.).
        """
        raise NotImplementedError


@dataclass
class TransportModelClient:
    """Bridges :class:`ProviderTransport` to the ``ModelClient`` protocol.

    Converts a ``NormalizedResponse`` to the action-dict format expected by
    ``AgentLoop.run()``.  Returns a ``tool_calls`` batch action dict when the
    provider returns multiple simultaneous tool calls; ``AgentLoop._call_batch``
    handles parallel or serial dispatch depending on path independence.
    """

    transport: ProviderTransport
    registry: ToolRegistry

    async def next_action(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Dispatch to the transport and return an action dict."""
        tool_defs = self._build_tool_defs()
        response = await self.transport.complete(messages, tools=tool_defs)

        if not response.tool_calls:
            return {"type": "final_answer", "content": response.content}

        if len(response.tool_calls) == 1:
            tc = response.tool_calls[0]
            return {
                "type": "tool_call",
                "tool": tc.name,
                "id": tc.id,
                "arguments": repair_json_args(tc.arguments),
            }

        # Multiple tool calls — return a batch action for AgentLoop._call_batch
        return {
            "type": "tool_calls",
            "calls": [
                {
                    "tool": tc.name,
                    "id": tc.id,
                    "arguments": repair_json_args(tc.arguments),
                }
                for tc in response.tool_calls
            ],
        }

    def _build_tool_defs(self) -> list[dict[str, Any]]:
        """Convert registered schemas to a provider-agnostic tool list."""
        return [
            {
                "name": s.name,
                "description": s.description,
                "parameters": s.parameters,
            }
            for s in self.registry.schemas()
        ]
