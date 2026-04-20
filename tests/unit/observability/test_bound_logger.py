"""Tests for observability.molecules.bound_logger."""

from __future__ import annotations

from typing import Any

from pyarnes_core.observability import log_error, log_event, log_warning
from pyarnes_core.observability.ports import LoggerPort


class RecordingLogger:
    """Minimal fake satisfying LoggerPort; captures calls for assertion."""

    def __init__(self) -> None:
        self.bound: dict[str, Any] = {}
        self.events: list[tuple[str, str, dict[str, Any]]] = []

    def bind(self, **kwargs: Any) -> RecordingLogger:
        self.bound = kwargs
        return self

    def info(self, message: str, *_args: Any, **_kwargs: Any) -> None:
        self.events.append(("info", message, dict(self.bound)))

    def warning(self, message: str, *_args: Any, **_kwargs: Any) -> None:
        self.events.append(("warning", message, dict(self.bound)))

    def error(self, message: str, *_args: Any, **_kwargs: Any) -> None:
        self.events.append(("error", message, dict(self.bound)))


class TestLogEvent:
    """log_event attaches fields via bind() so they land in record.extra."""

    def test_event_recorded_with_bound_fields(self) -> None:
        fake = RecordingLogger()
        log_event(fake, "lifecycle.transition", from_phase="init", to_phase="running")
        level, event, extra = fake.events[0]
        assert level == "info"
        assert event == "lifecycle.transition"
        assert extra == {"from_phase": "init", "to_phase": "running"}

    def test_event_name_passed_through_verbatim(self) -> None:
        """The event name is handed to info() untouched — no format interpolation."""
        fake = RecordingLogger()
        log_event(fake, "plain.event", kind="a")
        _, event, _ = fake.events[0]
        assert event == "plain.event"

    def test_warning_level(self) -> None:
        fake = RecordingLogger()
        log_warning(fake, "guardrail.blocked", tool="shell")
        assert fake.events[0][0] == "warning"

    def test_error_level(self) -> None:
        fake = RecordingLogger()
        log_error(fake, "tool.failed", reason="boom")
        assert fake.events[0][0] == "error"


class TestLoggerPortIsStructural:
    """Any object with bind/info/warning/error satisfies LoggerPort."""

    def test_recording_logger_satisfies_port(self) -> None:
        assert isinstance(RecordingLogger(), LoggerPort)
