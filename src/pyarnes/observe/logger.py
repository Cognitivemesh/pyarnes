"""Structured JSONL logging — single point of observability.

All harness components log through this module so that every event is:

1. **Structured** — key-value pairs, not free-form strings.
2. **JSONL-serialised** — one JSON object per line, easy for agents to parse.
3. **Configurable** — switch between human-readable (dev) and JSONL (CI/prod).
"""

from __future__ import annotations

import logging
import sys
from typing import TextIO

import structlog


def configure_logging(
    *,
    level: int = logging.INFO,
    json: bool = True,
    stream: TextIO = sys.stderr,
) -> None:
    """Set up structlog with JSONL (default) or console rendering.

    Call once at application startup.  Subsequent calls reconfigure
    the global settings.

    Args:
        level: Minimum log level.
        json: When ``True`` emit JSONL; otherwise pretty-print for humans.
        stream: Output stream (defaults to stderr so stdout stays clean
                for tool results).
    """
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if json:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
        final_processors = [*shared_processors, structlog.processors.format_exc_info, renderer]
    else:
        renderer = structlog.dev.ConsoleRenderer()
        final_processors = [*shared_processors, renderer]

    structlog.configure(
        processors=final_processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=stream),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger.

    Args:
        name: Logger name (usually ``__name__``).

    Returns:
        A bound logger instance.
    """
    return structlog.get_logger(name)  # type: ignore[return-value]
