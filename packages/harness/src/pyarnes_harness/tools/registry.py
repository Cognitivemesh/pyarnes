"""Tool registry — discover, register, and validate tool handlers.

Not safe for concurrent mutation. ``register`` and ``unregister`` do
classic check-then-mutate sequences; expect a single owner task per
registry. Concurrent dispatch is not part of the current design.

Self-registration
-----------------
Use the :func:`tool` decorator to register a handler class at *import time*
into the module-level :data:`_global` registry.  Call
:func:`global_registry` to retrieve it, or set
``AgentRuntime.use_global_registry = True`` to merge it automatically.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeVar

from pyarnes_core.observability import log_event
from pyarnes_core.observe.logger import get_logger
from pyarnes_core.types import ToolHandler

__all__ = [
    "ToolRegistry",
    "ToolSchema",
    "global_registry",
    "tool",
]


@dataclass(frozen=True)
class ToolSchema:
    """Provider-agnostic tool schema for schema conversion in transport adapters."""

    name: str
    description: str
    parameters: dict[str, Any]


_T = TypeVar("_T")

logger = get_logger(__name__)


class ToolRegistry:
    """Central registry for agentic tool handlers.

    Stores :class:`~pyarnes_core.types.ToolHandler` instances keyed by name.
    Validates that handlers are proper ``ToolHandler`` subclasses on
    registration.

    Usage::

        registry = ToolRegistry()
        registry.register("read_file", ReadFileTool())
        handler = registry.get("read_file")
    """

    def __init__(self) -> None:
        """Initialise an empty tool registry."""
        self._tools: dict[str, ToolHandler] = {}
        self._schemas: dict[str, ToolSchema] = {}

    def register(self, name: str, handler: ToolHandler) -> None:
        """Register a tool handler under the given name.

        Args:
            name: Unique tool name.
            handler: A ``ToolHandler`` subclass instance.

        Raises:
            ValueError: If *name* is already registered.
            TypeError: If *handler* is not a ``ToolHandler`` subclass instance.
        """
        if name in self._tools:
            msg = f"Tool '{name}' is already registered"
            raise ValueError(msg)
        if not isinstance(handler, ToolHandler):
            msg = (
                f"Handler for '{name}' does not satisfy ToolHandler (must define `async def execute(self, arguments)`)"
            )
            raise TypeError(msg)
        self._tools[name] = handler
        log_event(logger, "registry.registered", tool=name)

    def get(self, name: str) -> ToolHandler | None:
        """Look up a handler by name, returning ``None`` if missing."""
        return self._tools.get(name)

    def unregister(self, name: str) -> None:
        """Remove a tool from the registry.

        Args:
            name: Tool name to remove.

        Raises:
            KeyError: If the tool is not registered.
        """
        if name not in self._tools:
            msg = f"Tool '{name}' is not registered"
            raise KeyError(msg)
        del self._tools[name]
        log_event(logger, "registry.unregistered", tool=name)

    @property
    def names(self) -> list[str]:
        """Return sorted list of registered tool names."""
        return sorted(self._tools)

    def register_schema(self, name: str, schema: ToolSchema) -> None:
        """Store a JSON-Schema definition for a tool.

        Args:
            name: Tool name (does not need a matching handler entry).
            schema: Provider-agnostic :class:`ToolSchema`.

        Raises:
            ValueError: If a schema for *name* is already registered.
        """
        if name in self._schemas:
            msg = f"Schema for '{name}' is already registered"
            raise ValueError(msg)
        self._schemas[name] = schema

    def schemas(self) -> list[ToolSchema]:
        """Return all registered schemas in insertion order."""
        return list(self._schemas.values())

    def as_dict(self) -> dict[str, ToolHandler]:
        """Return a shallow copy of the internal mapping."""
        return dict(self._tools)

    def __len__(self) -> int:  # noqa: D105
        return len(self._tools)

    def __contains__(self, name: str) -> bool:  # noqa: D105
        return name in self._tools

    def __repr__(self) -> str:  # noqa: D105
        return f"ToolRegistry(tools={self.names!r})"


# ── Global self-registration surface ──────────────────────────────────────

_global: ToolRegistry = ToolRegistry()


def global_registry() -> ToolRegistry:
    """Return the module-level registry populated by ``@tool`` decorators."""
    return _global


def tool(name: str) -> type[_T]:  # type: ignore[return]
    """Class decorator that registers the decorated class in the global registry.

    The class is instantiated with no arguments on decoration, so tool classes
    must be constructible without parameters.

    Example::

        @tool("read_file")
        class ReadFileTool:
            async def execute(self, arguments): ...
    """

    def decorator(cls: type[_T]) -> type[_T]:
        _global.register(name, cls())  # type: ignore[arg-type]
        return cls

    return decorator  # type: ignore[return-value]
