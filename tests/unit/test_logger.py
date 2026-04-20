"""Tests for the structured JSONL logger."""

from __future__ import annotations

import io
import json

from pyarnes_core.observe.logger import configure_logging, get_logger


class TestConfigureLogging:
    """Logger configuration produces JSONL output."""

    def test_json_output(self) -> None:
        buf = io.StringIO()
        configure_logging(level="DEBUG", json=True, stream=buf)
        log = get_logger("test.json")
        log.info("hello")

        line = buf.getvalue().strip()
        data = json.loads(line)
        assert data["event"] == "hello"
        assert "timestamp" in data
        assert data["level"] == "info"

    def test_console_output(self) -> None:
        buf = io.StringIO()
        configure_logging(level="DEBUG", json=False, stream=buf)
        log = get_logger("test.console")
        log.info("visible")

        output = buf.getvalue()
        assert "visible" in output

    def test_extra_sinks_receive_events(self) -> None:
        # D16: callers that need a side-channel sink can register it
        # on configure_logging so it survives reconfigures.
        captured: list[str] = []

        def side_sink(message: object) -> None:
            captured.append(str(message).strip())

        buf = io.StringIO()
        configure_logging(level="DEBUG", json=True, stream=buf, extra_sinks=[side_sink])
        log = get_logger("test.extra")
        log.info("side-channel")
        assert any("side-channel" in line for line in captured)
