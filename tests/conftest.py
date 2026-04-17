"""Shared pytest fixtures and configuration."""

from __future__ import annotations

import logging

import structlog

from pyarnes.observe.logger import configure_logging


def pytest_configure() -> None:
    """Configure structured logging for test runs (human-readable)."""
    configure_logging(level=logging.DEBUG, json=False)


# Re-export for convenience in tests
__all__ = ["configure_logging", "structlog"]
