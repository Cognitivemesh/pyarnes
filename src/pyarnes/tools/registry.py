"""Tool registry — discover, register, and validate tool handlers."""

from __future__ import annotations

from pyarnes.observe.logger import get_logger
from pyarnes.types import ToolHandler

__all__ = [
    "ToolRegistry",
]

logger = get_logger(__name__)


class ToolRegistry:
    """Central registry for agentic tool handlers.

    Stores :class:`~pyarnes.types.ToolHandler` instances keyed by name.
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
            msg = f"Handler for '{name}' does not satisfy ToolHandler (must subclass ToolHandler ABC)"
            raise TypeError(msg)
        self._tools[name] = handler
        logger.info("registry.registered tool={tool}", tool=name)

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
        logger.info("registry.unregistered tool={tool}", tool=name)

    @property
    def names(self) -> list[str]:
        """Return sorted list of registered tool names."""
        return sorted(self._tools)

    def as_dict(self) -> dict[str, ToolHandler]:
        """Return a shallow copy of the internal mapping."""
        return dict(self._tools)

    def __len__(self) -> int:  # noqa: D105
        return len(self._tools)

    def __contains__(self, name: str) -> bool:  # noqa: D105
        return name in self._tools

    def __repr__(self) -> str:  # noqa: D105
        return f"ToolRegistry(tools={self.names!r})"
