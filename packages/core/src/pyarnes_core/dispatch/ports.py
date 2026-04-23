"""Dispatch domain ports — structural contracts for the loop's collaborators.

``ToolHandler`` and ``ModelClient`` are ``@runtime_checkable`` Protocols
so any class with the right async method signature satisfies them —
no forced subclass. ``isinstance()`` keeps working because
``@runtime_checkable``.

``pyarnes_core.types`` re-exports these for backward compatibility with
code that imported from the old location.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = [
    "JudgeClient",
    "ModelClient",
    "ToolHandler",
]


@runtime_checkable
class ToolHandler(Protocol):
    """Structural contract for every tool the harness can invoke.

    Any class implementing ``async def execute(self, arguments) -> Any``
    satisfies this Protocol and can be registered with ``ToolRegistry``.

    Example::

        import asyncio
        from pathlib import Path


        class ReadFileTool:
            async def execute(self, arguments: dict[str, Any]) -> Any:
                path = arguments["path"]
                return await asyncio.to_thread(Path(path).read_text)
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
class JudgeClient(Protocol):
    """Structural contract for a free-form LLM judge.

    Separate from ``ModelClient`` because judge calls take a plain-text
    prompt and return a text response — they do not dispatch tool calls.
    Any client implementing ``async def judge(self, prompt)`` satisfies
    this protocol without inheritance.
    """

    async def judge(self, prompt: str) -> str:
        """Call the LLM with a plain-text prompt and return its response.

        Args:
            prompt: The evaluation prompt to send to the LLM.

        Returns:
            The LLM's text response.
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
