"""Structured JSONL logging — single point of observability.

All harness components log through this module so that every event is:

1. **Structured** — key-value pairs, not free-form strings.
2. **JSONL-serialised** — one JSON object per line, easy for agents to parse.
3. **Configurable** — switch between human-readable (dev) and JSONL (CI/prod).

Uses `loguru <https://loguru.readthedocs.io/>`_ as the logging backend.
"""

from __future__ import annotations

import json
import sys
from enum import Enum
from typing import TextIO

from loguru import logger

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


def _json_serializer(message: object) -> str:
    """Serialize a loguru record as a single JSON line."""
    record = message.record  # type: ignore[union-attr]
    payload = {
        "timestamp": record["time"].isoformat(),
        "level": record["level"].name.lower(),
        "event": record["message"],
        **record["extra"],
    }
    return json.dumps(payload, default=str, ensure_ascii=False)


def _json_sink(message: object) -> None:
    """Write a JSONL-formatted log line to the configured stream."""
    line = _json_serializer(message)
    _active_stream.write(line + "\n")
    _active_stream.flush()


# Module-level stream reference (defaults to stderr).
_active_stream: TextIO = sys.stderr


def configure_logging(
    *,
    level: str | int = "INFO",
    json: bool = True,
    stream: TextIO = sys.stderr,
    fmt: LogFormat | None = None,
) -> None:
    """Set up loguru with JSONL (default) or console rendering.

    Call once at application startup.  Subsequent calls reconfigure
    the global settings.

    Args:
        level: Minimum log level (name or numeric).
        json: When ``True`` emit JSONL; otherwise pretty-print for humans.
            Ignored when *fmt* is provided.
        stream: Output stream (defaults to stderr so stdout stays clean
                for tool results).
        fmt: Explicit format selection.  When provided, overrides *json*.
    """
    global _active_stream  # noqa: PLW0603
    _active_stream = stream

    use_json = fmt == LogFormat.JSON if fmt is not None else json

    # Normalise numeric levels to string names for loguru.
    if isinstance(level, int):
        _level_map = {10: "DEBUG", 20: "INFO", 30: "WARNING", 40: "ERROR", 50: "CRITICAL"}
        level = _level_map.get(level, "INFO")

    # Remove all existing handlers, then add the new one.
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


def get_logger(name: str | None = None) -> logger.__class__:  # type: ignore[name-defined]
    """Return a bound loguru logger.

    Args:
        name: Logger name (usually ``__name__``).

    Returns:
        A loguru logger instance, optionally bound with *name*.
    """
    if name:
        return logger.bind(logger_name=name)
    return logger
