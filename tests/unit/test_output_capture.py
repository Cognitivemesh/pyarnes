"""Adversarial tests for OutputCapture.

The basic happy-path and redactor tests live in test_capture.py.
This file adds:
- Redactor is called with the correct field values (not silently skipped)
- Redacted content does not leak into the stored record
- Exception fields are serialized as strings, not raw exception objects
- Large output is stored without truncation
- Unicode and structurally unusual content handled without errors
"""

from __future__ import annotations

from typing import Any

from pyarnes_harness.capture.output import CapturedOutput, OutputCapture


class TestRedactorContract:
    """Redactor receives the correct payload and its output is stored."""

    def test_redactor_receives_stdout_content(self) -> None:
        calls: list[str] = []

        def redactor(payload: dict[str, Any]) -> dict[str, Any]:
            calls.append(payload.get("stdout", ""))
            return payload

        capture = OutputCapture(redactor=redactor)
        capture.record_success("tool", {}, stdout="sensitive output")
        assert calls == ["sensitive output"]

    def test_redactor_receives_stderr_content(self) -> None:
        calls: list[str] = []

        def redactor(payload: dict[str, Any]) -> dict[str, Any]:
            calls.append(payload.get("stderr", ""))
            return payload

        capture = OutputCapture(redactor=redactor)
        capture.record_success("tool", {}, stderr="error text")
        assert calls == ["error text"]

    def test_redacted_stdout_replaces_original(self) -> None:
        def redactor(payload: dict[str, Any]) -> dict[str, Any]:
            p = dict(payload)
            p["stdout"] = "[REDACTED]"
            return p

        capture = OutputCapture(redactor=redactor)
        record = capture.record_success("tool", {}, stdout="SECRET_VALUE")
        assert record.stdout == "[REDACTED]"
        assert "SECRET_VALUE" not in record.stdout

    def test_redacted_arguments_do_not_leak(self) -> None:
        def redactor(payload: dict[str, Any]) -> dict[str, Any]:
            p = dict(payload)
            p["arguments"] = dict.fromkeys(p["arguments"], "***")
            return p

        capture = OutputCapture(redactor=redactor)
        record = capture.record_success(
            "login",
            {"username": "alice", "password": "hunter2"},
        )
        assert record.arguments == {"username": "***", "password": "***"}

    def test_redactor_called_on_failure_path(self) -> None:
        calls: list[bool] = []

        def redactor(payload: dict[str, Any]) -> dict[str, Any]:
            calls.append(True)
            return payload

        capture = OutputCapture(redactor=redactor)
        capture.record_failure("tool", {}, RuntimeError("boom"))
        assert calls == [True]


class TestExceptionSerialization:
    """Exceptions must be stored as strings, never as raw exception objects."""

    def test_error_field_is_str(self) -> None:
        capture = OutputCapture()
        record = capture.record_failure("tool", {}, RuntimeError("bang"))
        assert isinstance(record.error, str)
        assert "bang" in (record.error or "")

    def test_traceback_field_is_str(self) -> None:
        capture = OutputCapture()
        exc = ValueError("bad value")
        record = capture.record_failure("tool", {}, exc)
        assert isinstance(record.traceback_str, str)
        assert len(record.traceback_str) > 0

    def test_chained_exception_traceback_is_str(self) -> None:
        def _raise_chained() -> None:
            inner = RuntimeError("root cause")
            raise ValueError("wrapper") from inner

        capture = OutputCapture()
        try:
            _raise_chained()
        except ValueError as exc:
            record = capture.record_failure("tool", {}, exc)
        assert isinstance(record.traceback_str, str)
        assert "root cause" in (record.traceback_str or "")

    def test_succeeded_is_false_when_error_present(self) -> None:
        capture = OutputCapture()
        record = capture.record_failure("tool", {}, OSError("disk full"))
        assert record.succeeded is False


class TestLargeAndUnicodeContent:
    """OutputCapture must not truncate or mangle content."""

    def test_10mb_stdout_not_truncated(self) -> None:
        capture = OutputCapture()
        large = "x" * (10 * 1024 * 1024)
        record = capture.record_success("tool", {}, stdout=large)
        assert len(record.stdout) == 10 * 1024 * 1024

    def test_emoji_and_unicode_content_preserved(self) -> None:
        capture = OutputCapture()
        content = "🔑🚀🎯日本語привет" * 500
        record = capture.record_success("tool", {}, stdout=content)
        assert record.stdout == content

    def test_zero_width_chars_not_stripped(self) -> None:
        capture = OutputCapture()
        content = "result" + chr(0x200D) + "value"
        record = capture.record_success("tool", {}, stdout=content)
        assert record.stdout == content

    def test_empty_stdout_and_stderr_defaults(self) -> None:
        capture = OutputCapture()
        record = capture.record_success("tool", {"key": "val"})
        assert record.stdout == ""
        assert record.stderr == ""


class TestCapturedOutputAsDict:
    """as_dict must include all schema keys required by downstream consumers."""

    def test_all_schema_keys_present(self) -> None:
        record = CapturedOutput(tool_name="t", return_value=42)
        d = record.as_dict()
        for key in (
            "tool_name",
            "arguments",
            "stdout",
            "stderr",
            "return_value",
            "error",
            "traceback",
            "duration_seconds",
            "timestamp",
            "succeeded",
        ):
            assert key in d, f"missing key: {key}"

    def test_timestamp_is_positive_float(self) -> None:
        record = CapturedOutput(tool_name="t")
        d = record.as_dict()
        assert isinstance(d["timestamp"], float)
        assert d["timestamp"] > 0
