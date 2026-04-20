"""Observability domain ports.

Structural contracts for the objects that flow through the logging
pipeline. Kept minimal — only what the atoms and molecules need. The
concrete loguru logger satisfies :class:`LoggerPort` by virtue of
having matching ``bind`` / ``info`` / ``warning`` / ``error`` methods.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = [
    "LoggerPort",
]


@runtime_checkable
class LoggerPort(Protocol):
    """Minimal logger surface used by the observability molecules."""

    def bind(self, **kwargs: Any) -> LoggerPort:
        """Return a new logger with *kwargs* attached as structured fields."""
        ...

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Emit an info-level record."""
        ...

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Emit a warning-level record."""
        ...

    def error(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Emit an error-level record."""
        ...
