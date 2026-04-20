"""Shared Protocol definitions for the harness contracts.

Centralises the core contracts (``ToolHandler``, ``ModelClient``) as
``@runtime_checkable`` Protocols so any class with the right shape —
including third-party handlers without a direct import dependency on
pyarnes — satisfies them structurally. The previous ABC form forced
every handler to subclass ``ToolHandler`` explicitly; Protocols keep
the same ``isinstance`` check working without that constraint.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = [
    "ModelClient",
    "ToolHandler",
]


@runtime_checkable
class ToolHandler(Protocol):
    """Structural contract for every tool the harness can invoke.

    Any class implementing ``async def execute(self, arguments) -> Any``
    satisfies this Protocol and can be registered with ``ToolRegistry``.

    Example::

        class ReadFileTool:
            async def execute(self, arguments: dict[str, Any]) -> Any:
                path = arguments["path"]
                return Path(path).read_text()
    """

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Run the tool with the given arguments.

        Args:
            arguments: Key-value arguments for the tool invocation.

        Returns:
            The tool's result (will be serialized for the model).
        """
        ...


@runtime_checkable
class ModelClient(Protocol):
    """Structural contract for the backing LLM client.

    Any class implementing ``async def next_action(self, messages)``
    satisfies this Protocol — plug in any provider (OpenAI,
    Anthropic, local, …) without inheriting from this file.
    """

    async def next_action(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Return the next action (``tool_call`` or ``final_answer``).

        Args:
            messages: Full conversation history so far.

        Returns:
            A dict describing either a ``tool_call`` or ``final_answer``.
        """
        ...
