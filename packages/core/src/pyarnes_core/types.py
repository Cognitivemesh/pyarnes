"""Shared abstract base classes and type definitions.

Centralises the core contracts (``ToolHandler``, ``ModelClient``) so that
every module references a single source of truth rather than duplicating
Protocol definitions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

__all__ = [
    "ModelClient",
    "ToolHandler",
]


class ToolHandler(ABC):
    """Abstract base for every tool the harness can invoke.

    Subclass and implement :meth:`execute` to create a concrete tool.

    Example::

        import asyncio
        from pathlib import Path

        class ReadFileTool(ToolHandler):
            async def execute(self, arguments: dict[str, Any]) -> Any:
                path = arguments["path"]
                return await asyncio.to_thread(Path(path).read_text)
    """

    @abstractmethod
    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Run the tool with the given arguments.

        Args:
            arguments: Key-value arguments for the tool invocation.

        Returns:
            The tool's result (will be stringified for the model).
        """


class ModelClient(ABC):
    """Abstract base for the backing LLM client.

    Subclass and implement :meth:`next_action` to plug in any model
    provider (OpenAI, Anthropic, local, …).
    """

    @abstractmethod
    async def next_action(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Return the next action (tool_call or final answer).

        Args:
            messages: Full conversation history so far.

        Returns:
            A dict describing either a ``tool_call`` or ``final_answer``.
        """
