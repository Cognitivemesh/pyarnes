"""Shared pytest fixtures and configuration."""

from __future__ import annotations

from pyarnes_core.observe.logger import configure_logging


def pytest_configure() -> None:
    """Configure structured logging for test runs (human-readable)."""
    configure_logging(level="DEBUG", json=False)


__all__ = ["configure_logging"]
