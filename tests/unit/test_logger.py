"""Tests for the structured JSONL logger."""

from __future__ import annotations

import io
import json
import logging

from pyarnes.observe.logger import configure_logging, get_logger


class TestConfigureLogging:
    """Logger configuration produces JSONL output."""

    def test_json_output(self) -> None:
        buf = io.StringIO()
        configure_logging(level=logging.DEBUG, json=True, stream=buf)
        log = get_logger("test.json")
        log.info("hello", key="value")

        line = buf.getvalue().strip()
        data = json.loads(line)
        assert data["event"] == "hello"
        assert data["key"] == "value"
        assert "timestamp" in data
        assert data["log_level"] == "info"

    def test_console_output(self) -> None:
        buf = io.StringIO()
        configure_logging(level=logging.DEBUG, json=False, stream=buf)
        log = get_logger("test.console")
        log.info("visible")

        output = buf.getvalue()
        assert "visible" in output
