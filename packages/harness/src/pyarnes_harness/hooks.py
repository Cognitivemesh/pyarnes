"""Pre/post tool-call middleware hooks for the agent loop.

Cross-cutting concerns (logging, rate limiting, result transformation, early
termination) can be implemented as hooks without modifying tool handlers.
Hooks are async-first and run in declaration order.

Pre-hooks receive the tool name and arguments; they return modified arguments
(or ``None`` to leave them unchanged) and may raise ``LLMRecoverableError``
to veto the tool call. Post-hooks receive the tool name, arguments, result,
and error flag; they return a (possibly modified) result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

__all__ = [
    "HookChain",
    "PostToolHook",
    "PreToolHook",
]


class PreToolHook(Protocol):
    """Hook called before a tool executes.

    Return modified arguments dict, or ``None`` to leave arguments unchanged.
    Raise ``LLMRecoverableError`` to veto the call entirely.
    """

    async def __call__(  # noqa: D102
        self, tool: str, arguments: dict[str, Any]
    ) -> dict[str, Any] | None: ...


class PostToolHook(Protocol):
    """Hook called after a tool executes (success or error).

    Return the (possibly modified) result. Raising an exception overrides
    the normal error path.
    """

    async def __call__(  # noqa: D102
        self,
        tool: str,
        arguments: dict[str, Any],
        result: Any,
        *,
        is_error: bool,
    ) -> Any: ...


@dataclass
class HookChain:
    """Ordered chain of pre- and post-tool-call hooks.

    Attributes:
        pre: Hooks run before tool execution, in declaration order.
        post: Hooks run after tool execution, in declaration order.
    """

    pre: list[PreToolHook] = field(default_factory=list)
    post: list[PostToolHook] = field(default_factory=list)

    async def run_pre(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Run all pre-hooks in order, threading argument mutations through.

        Args:
            tool: Tool name being called.
            arguments: Original arguments from the action.

        Returns:
            Final (possibly mutated) arguments dict.

        Raises:
            LLMRecoverableError: If any hook vetoes the tool call.
        """
        current = dict(arguments)
        for hook in self.pre:
            modified = await hook(tool, current)
            if modified is not None:
                current = modified
        return current

    async def run_post(
        self,
        tool: str,
        arguments: dict[str, Any],
        result: Any,
        *,
        is_error: bool,
    ) -> Any:
        """Run all post-hooks in order, threading result mutations through.

        Args:
            tool: Tool name that was called.
            arguments: Arguments that were passed to the tool.
            result: Raw result (or error description string).
            is_error: Whether the call ended in failure.

        Returns:
            Final (possibly transformed) result.
        """
        current = result
        for hook in self.post:
            current = await hook(tool, arguments, current, is_error=is_error)
        return current
