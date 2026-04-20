"""Molecule: bound_logger — ``bind(**kv).info(event)`` behind one call.

The widespread ``logger.info("foo bar={x}", x=...)`` pattern renders
the kwargs into the message string and leaves ``record["extra"]``
empty, so ``jq '.bar == "baz"'`` never matches anything. This molecule
forces the correct ``bind + event-name`` shape so the fields land in
``extra`` and the JSON serializer includes them.
"""

from __future__ import annotations

from typing import Any

from pyarnes_core.observability.ports import LoggerPort

__all__ = [
    "log_error",
    "log_event",
    "log_warning",
]


def log_event(logger: LoggerPort, event: str, /, **fields: Any) -> None:
    """Emit *event* at INFO level with *fields* as structured extra.

    Args:
        logger: A logger satisfying :class:`LoggerPort`.
        event: Event name (e.g. ``"lifecycle.transition"``).
        **fields: Key-value fields attached to the record's ``extra``.
    """
    logger.bind(**fields).info(event)


def log_warning(logger: LoggerPort, event: str, /, **fields: Any) -> None:
    """Emit *event* at WARNING level with *fields* as structured extra."""
    logger.bind(**fields).warning(event)


def log_error(logger: LoggerPort, event: str, /, **fields: Any) -> None:
    """Emit *event* at ERROR level with *fields* as structured extra."""
    logger.bind(**fields).error(event)
