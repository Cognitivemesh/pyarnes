"""Registry for custom async recovery strategies per error type.

Lets adopters register handlers for specific ``HarnessError`` subtypes without
modifying core code.  The registry is consulted in the ``HarnessError`` catch-all
branch of ``AgentLoop._call_tool``; returning a non-``None`` value short-circuits
the default ``UnexpectedError`` raise so the loop can continue.

Design choices
--------------
* **Exact-type dispatch** — looks up ``type(exc)`` directly in the handler map.
  No MRO walk is performed; callers who want base-class coverage register the base
  explicitly.
* **Return type is ``object | None``** — the registry lives in core, which cannot
  import ``ToolMessage`` from harness (that would create a circular dependency).
  The caller (in harness) casts the result with ``typing.cast``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pyarnes_core.errors import HarnessError

__all__ = ["AsyncHandler", "ErrorHandlerRegistry"]

# Async callable that receives a HarnessError and returns an optional replacement
# result.  Returning ``None`` means "fall through to default handling."
AsyncHandler = Callable[[HarnessError], Awaitable[Any | None]]


@dataclass(slots=True)
class ErrorHandlerRegistry:
    """Registry of custom async recovery handlers keyed by error type.

    Attributes:
        _handlers: Map from ``HarnessError`` subtype to its async handler.
    """

    _handlers: dict[type[HarnessError], AsyncHandler] = field(default_factory=dict)

    def register(self, error_type: type[HarnessError], handler: AsyncHandler) -> None:
        """Register a custom handler for a specific error type.

        Args:
            error_type: The exact ``HarnessError`` subclass to handle.
            handler: Async callable invoked when that error type is raised.
                     Must return a replacement result or ``None`` to fall through.
        """
        self._handlers[error_type] = handler

    async def dispatch(self, exc: HarnessError) -> object | None:
        """Invoke the registered handler for *exc*, if any.

        Uses exact-type lookup — subclass matches are not considered.

        Args:
            exc: The error that was caught.

        Returns:
            The handler's return value (to be cast to ``ToolMessage`` by the
            caller), or ``None`` when no handler is registered or the handler
            itself returns ``None``.
        """
        handler = self._handlers.get(type(exc))
        if handler is None:
            return None
        return await handler(exc)
