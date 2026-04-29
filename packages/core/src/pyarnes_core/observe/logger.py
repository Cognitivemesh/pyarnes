"""Structured JSONL logging — single point of observability.

All harness components log through this module so that every event is:

1. **Structured** — key-value pairs, not free-form strings.
2. **JSONL-serialised** — one JSON object per line, easy for agents to parse.
3. **Configurable** — switch between human-readable (dev) and JSONL (CI/prod).

Uses `loguru <https://loguru.readthedocs.io/>`_ as the logging backend.

Callers should emit events via ``log_event`` / ``log_warning`` /
``log_error`` from ``pyarnes_core.observability.molecules`` rather
than ``logger.info("msg key={v}", v=...)``. The molecule form
puts kwargs in ``record["extra"]`` where the JSON serializer can
find them (D15).
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from contextvars import ContextVar
from enum import Enum
from typing import TYPE_CHECKING, Any, TextIO

from loguru import logger

from pyarnes_core.observability import dumps

if TYPE_CHECKING:
    from loguru import Logger

__all__ = [
    "LogFormat",
    "configure_logging",
    "get_logger",
]


class LogFormat(Enum):
    """Supported log output formats.

    Attributes:
        JSON: One JSON object per line (for CI / production / agent parsing).
        CONSOLE: Coloured, human-readable output (for local development).
    """

    JSON = "json"
    CONSOLE = "console"


def _json_serializer(message: Any) -> str:
    """Serialize a loguru record as a single JSON line."""
    record = message.record
    payload = {
        "timestamp": record["time"].isoformat(),
        "level": record["level"].name.lower(),
        "event": record["message"],
        **record["extra"],
    }
    scrub = _active_scrub.get()
    if scrub is not None:
        payload = scrub(payload)
    return dumps(payload)


def _json_sink(message: Any) -> None:
    """Write a JSONL-formatted log line to the configured stream."""
    line = _json_serializer(message)
    stream = _active_stream.get()
    stream.write(line + "\n")
    stream.flush()


# Per-task stream reference — ContextVar gives async-safe isolation.
_active_stream: ContextVar[TextIO] = ContextVar("_active_stream", default=sys.stderr)

# Per-task scrub callable — isolated per asyncio Task via ContextVar.
_active_scrub: ContextVar[Callable[[dict[str, Any]], dict[str, Any]] | None] = ContextVar("_active_scrub", default=None)


def configure_logging(  # noqa: PLR0913
    *,
    level: str | int = "INFO",
    json: bool = True,
    stream: TextIO = sys.stderr,
    fmt: LogFormat | None = None,
    extra_sinks: list[Callable[[Any], None]] | None = None,
    scrub: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> None:
    """Set up loguru with JSONL (default) or console rendering.

    ``configure_logging`` owns the default sink set — calling it a
    second time removes every handler loguru knows about, including
    anything a caller added via ``loguru.logger.add(...)`` in between.
    Callers that need extra sinks should declare them here via
    *extra_sinks* so they are re-attached on every reconfigure.

    Args:
        level: Minimum log level (name or numeric).
        json: When ``True`` emit JSONL; otherwise pretty-print for humans.
            Ignored when *fmt* is provided.
        stream: Output stream (defaults to stderr so stdout stays clean
                for tool results).
        fmt: Explicit format selection.  When provided, overrides *json*.
        extra_sinks: Optional extra sinks (callables accepting a loguru
            message) to install alongside the default sink.
        scrub: Optional JSON payload transformer applied before writing.
            Used to redact secrets (e.g. drop ``authorization`` keys).
            Only takes effect for JSON output.
    """
    _active_stream.set(stream)
    _active_scrub.set(scrub)

    use_json = fmt == LogFormat.JSON if fmt is not None else json

    # Normalise numeric levels to string names for loguru.
    if isinstance(level, int):
        _level_map = {10: "DEBUG", 20: "INFO", 30: "WARNING", 40: "ERROR", 50: "CRITICAL"}
        level = _level_map.get(level, "INFO")

    # Remove all existing handlers, then add the new ones.
    logger.remove()
    if use_json:
        logger.add(_json_sink, level=level, format="{message}", colorize=False)
    else:
        logger.add(
            stream,
            level=level,
            format="<level>{level: <8}</level> | <cyan>{name}</cyan> - {message}",
            colorize=True,
        )
    for sink in extra_sinks or []:
        logger.add(sink, level=level, format="{message}", colorize=False)


def get_logger(name: str | None = None) -> Logger:
    """Return a bound loguru logger.

    Args:
        name: Logger name (usually ``__name__``).

    Returns:
        A loguru ``Logger`` — either the module singleton or a copy
        bound with ``logger_name=name``.
    """
    if name:
        return logger.bind(logger_name=name)
    return logger
