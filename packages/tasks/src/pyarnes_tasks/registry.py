"""Plugin registry — single source of truth for discovered tasks.

Mirrors :class:`pyarnes_harness.tools.registry.ToolRegistry`: same
``register / get / names / __contains__ / __len__`` surface. Not safe
for concurrent mutation; the loader is the single owner that mutates
during startup, and dispatch is read-only thereafter.
"""

from __future__ import annotations

from typing import Any

from pyarnes_core.observability import log_event
from pyarnes_core.observe.logger import get_logger

__all__ = ["PluginRegistry", "global_registry"]


_logger = get_logger(__name__)


class PluginRegistry:
    """Holds the ``{name: Plugin}`` mapping populated by the loader."""

    def __init__(self) -> None:
        """Initialise an empty registry."""
        self._plugins: dict[str, Any] = {}

    def register(self, name: str, plugin: Any) -> None:
        """Register *plugin* under *name*. Raises if *name* is taken."""
        if name in self._plugins:
            msg = f"Plugin {name!r} is already registered"
            raise ValueError(msg)
        self._plugins[name] = plugin
        log_event(_logger, "registry.registered", plugin=name)

    def get(self, name: str) -> Any | None:
        """Return the registered plugin or ``None`` if absent."""
        return self._plugins.get(name)

    def unregister(self, name: str) -> None:
        """Remove *name* from the registry. Raises ``KeyError`` if absent."""
        if name not in self._plugins:
            msg = f"Plugin {name!r} is not registered"
            raise KeyError(msg)
        del self._plugins[name]
        log_event(_logger, "registry.unregistered", plugin=name)

    def clear(self) -> None:
        """Drop every registered plugin (used by tests for isolation)."""
        self._plugins.clear()

    @property
    def names(self) -> list[str]:
        """Return all registered plugin names, sorted."""
        return sorted(self._plugins)

    def as_dict(self) -> dict[str, Any]:
        """Return a shallow copy of the underlying mapping."""
        return dict(self._plugins)

    def __contains__(self, name: str) -> bool:  # noqa: D105
        return name in self._plugins

    def __len__(self) -> int:  # noqa: D105
        return len(self._plugins)

    def __repr__(self) -> str:  # noqa: D105
        return f"PluginRegistry(plugins={self.names!r})"


_global: PluginRegistry = PluginRegistry()


def global_registry() -> PluginRegistry:
    """Return the module-level registry populated by ``Plugin`` subclasses."""
    return _global
