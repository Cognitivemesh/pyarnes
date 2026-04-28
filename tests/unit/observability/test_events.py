"""Tests for observability.molecules.events."""

from __future__ import annotations

from typing import Any

from pyarnes_core.observability import (
    log_guardrail_violation,
    log_lifecycle_transition,
    log_tool_call,
)


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


class TestLogLifecycleTransition:
    """log_lifecycle_transition emits event with all required context fields."""

    def test_event_name_is_lifecycle_transition(self) -> None:
        fake = RecordingLogger()
        log_lifecycle_transition(
            fake,
            "init",
            "running",
            session_id="s123",
            trace_id="t456",
            step=1,
        )
        _, event, _ = fake.events[0]
        assert event == "lifecycle.transition"

    def test_includes_phase_fields(self) -> None:
        fake = RecordingLogger()
        log_lifecycle_transition(
            fake,
            "running",
            "complete",
            session_id="s123",
            trace_id="t456",
            step=2,
        )
        _, _, extra = fake.events[0]
        assert extra["from_phase"] == "running"
        assert extra["to_phase"] == "complete"

    def test_includes_required_context_fields(self) -> None:
        fake = RecordingLogger()
        log_lifecycle_transition(
            fake,
            "init",
            "running",
            session_id="session-abc",
            trace_id="trace-def",
            step=5,
        )
        _, _, extra = fake.events[0]
        assert extra["session_id"] == "session-abc"
        assert extra["trace_id"] == "trace-def"
        assert extra["step"] == 5

    def test_missing_session_id_raises_type_error(self) -> None:
        fake = RecordingLogger()
        try:
            log_lifecycle_transition(
                fake,
                "init",
                "running",
                trace_id="t456",
                step=1,
            )
            raise AssertionError("Should have raised TypeError")
        except TypeError:
            pass

    def test_missing_trace_id_raises_type_error(self) -> None:
        fake = RecordingLogger()
        try:
            log_lifecycle_transition(
                fake,
                "init",
                "running",
                session_id="s123",
                step=1,
            )
            raise AssertionError("Should have raised TypeError")
        except TypeError:
            pass

    def test_missing_step_raises_type_error(self) -> None:
        fake = RecordingLogger()
        try:
            log_lifecycle_transition(
                fake,
                "init",
                "running",
                session_id="s123",
                trace_id="t456",
            )
            raise AssertionError("Should have raised TypeError")
        except TypeError:
            pass


class TestLogToolCall:
    """log_tool_call emits event with all required context fields."""

    def test_event_name_is_tool_call(self) -> None:
        fake = RecordingLogger()
        log_tool_call(
            fake,
            "shell",
            session_id="s123",
            trace_id="t456",
            step=1,
            duration_ms=42.5,
            is_error=False,
        )
        _, event, _ = fake.events[0]
        assert event == "tool.call"

    def test_includes_tool_fields(self) -> None:
        fake = RecordingLogger()
        log_tool_call(
            fake,
            "database",
            session_id="s123",
            trace_id="t456",
            step=2,
            duration_ms=123.45,
            is_error=True,
        )
        _, _, extra = fake.events[0]
        assert extra["tool_name"] == "database"
        assert extra["duration_ms"] == 123.45
        assert extra["is_error"] is True

    def test_includes_required_context_fields(self) -> None:
        fake = RecordingLogger()
        log_tool_call(
            fake,
            "shell",
            session_id="session-xyz",
            trace_id="trace-uvw",
            step=10,
            duration_ms=50.0,
            is_error=False,
        )
        _, _, extra = fake.events[0]
        assert extra["session_id"] == "session-xyz"
        assert extra["trace_id"] == "trace-uvw"
        assert extra["step"] == 10

    def test_missing_session_id_raises_type_error(self) -> None:
        fake = RecordingLogger()
        try:
            log_tool_call(
                fake,
                "shell",
                trace_id="t456",
                step=1,
                duration_ms=42.5,
                is_error=False,
            )
            raise AssertionError("Should have raised TypeError")
        except TypeError:
            pass

    def test_missing_trace_id_raises_type_error(self) -> None:
        fake = RecordingLogger()
        try:
            log_tool_call(
                fake,
                "shell",
                session_id="s123",
                step=1,
                duration_ms=42.5,
                is_error=False,
            )
            raise AssertionError("Should have raised TypeError")
        except TypeError:
            pass

    def test_missing_step_raises_type_error(self) -> None:
        fake = RecordingLogger()
        try:
            log_tool_call(
                fake,
                "shell",
                session_id="s123",
                trace_id="t456",
                duration_ms=42.5,
                is_error=False,
            )
            raise AssertionError("Should have raised TypeError")
        except TypeError:
            pass


class TestLogGuardrailViolation:
    """log_guardrail_violation emits event with all required context fields."""

    def test_event_name_is_guardrail_violation(self) -> None:
        fake = RecordingLogger()
        log_guardrail_violation(
            fake,
            "command_allowed_list",
            "shell",
            "Command not in allowed list",
            session_id="s123",
            trace_id="t456",
            step=1,
        )
        _, event, _ = fake.events[0]
        assert event == "guardrail.violation"

    def test_includes_violation_fields(self) -> None:
        fake = RecordingLogger()
        log_guardrail_violation(
            fake,
            "rate_limit",
            "api",
            "Exceeded rate limit",
            session_id="s123",
            trace_id="t456",
            step=2,
        )
        _, _, extra = fake.events[0]
        assert extra["guardrail"] == "rate_limit"
        assert extra["tool"] == "api"
        assert extra["reason"] == "Exceeded rate limit"

    def test_includes_required_context_fields(self) -> None:
        fake = RecordingLogger()
        log_guardrail_violation(
            fake,
            "pii_detector",
            "text_generation",
            "PII detected in output",
            session_id="session-123",
            trace_id="trace-456",
            step=7,
        )
        _, _, extra = fake.events[0]
        assert extra["session_id"] == "session-123"
        assert extra["trace_id"] == "trace-456"
        assert extra["step"] == 7

    def test_missing_session_id_raises_type_error(self) -> None:
        fake = RecordingLogger()
        try:
            log_guardrail_violation(
                fake,
                "guard1",
                "tool1",
                "reason1",
                trace_id="t456",
                step=1,
            )
            raise AssertionError("Should have raised TypeError")
        except TypeError:
            pass

    def test_missing_trace_id_raises_type_error(self) -> None:
        fake = RecordingLogger()
        try:
            log_guardrail_violation(
                fake,
                "guard1",
                "tool1",
                "reason1",
                session_id="s123",
                step=1,
            )
            raise AssertionError("Should have raised TypeError")
        except TypeError:
            pass

    def test_missing_step_raises_type_error(self) -> None:
        fake = RecordingLogger()
        try:
            log_guardrail_violation(
                fake,
                "guard1",
                "tool1",
                "reason1",
                session_id="s123",
                trace_id="t456",
            )
            raise AssertionError("Should have raised TypeError")
        except TypeError:
            pass
