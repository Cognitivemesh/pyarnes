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
        """Side-channel sinks survive reconfigures when registered here."""
        captured: list[str] = []

        def side_sink(message: object) -> None:
            captured.append(str(message).strip())

        buf = io.StringIO()
        configure_logging(level="DEBUG", json=True, stream=buf, extra_sinks=[side_sink])
        log = get_logger("test.extra")
        log.info("side-channel")
        assert any("side-channel" in line for line in captured)

    def test_scrub_redacts_payload_before_write(self) -> None:
        """``scrub`` rewrites the JSON payload before it reaches the sink."""
        buf = io.StringIO()

        def drop_authorization(payload: dict) -> dict:
            return {k: v for k, v in payload.items() if k != "authorization"}

        configure_logging(level="DEBUG", json=True, stream=buf, scrub=drop_authorization)
        log = get_logger("test.scrub")
        log.bind(authorization="Bearer secret", user_id=42).info("auth.check")

        data = json.loads(buf.getvalue().strip())
        assert "authorization" not in data
        assert data["user_id"] == 42
        assert data["event"] == "auth.check"

    def test_scrub_none_is_noop(self) -> None:
        """Omitting ``scrub`` (default) leaves the payload untouched."""
        buf = io.StringIO()
        configure_logging(level="DEBUG", json=True, stream=buf)
        log = get_logger("test.scrub.none")
        log.bind(marker="abc").info("keep")
        data = json.loads(buf.getvalue().strip())
        assert data["marker"] == "abc"
