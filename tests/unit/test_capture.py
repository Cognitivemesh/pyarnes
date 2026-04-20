"""Tests for capture module."""

from __future__ import annotations

from pyarnes_harness.capture.output import CapturedOutput, OutputCapture


class TestCapturedOutput:
    """CapturedOutput records and serialises tool results."""

    def test_success_record(self) -> None:
        record = CapturedOutput(
            tool_name="echo",
            arguments={"text": "hello"},
            return_value="hello",
            duration_seconds=0.01,
        )
        assert record.succeeded is True
        assert record.error is None

    def test_failure_record(self) -> None:
        record = CapturedOutput(
            tool_name="broken",
            error="something went wrong",
            traceback_str="Traceback...",
        )
        assert record.succeeded is False

    def test_as_dict_preserves_scalar_shape(self) -> None:
        # D17: return_value keeps its native JSON shape; no premature str().
        record = CapturedOutput(tool_name="test", return_value=42)
        d = record.as_dict()
        assert d["tool_name"] == "test"
        assert d["return_value"] == 42
        assert d["succeeded"] is True

    def test_as_dict_preserves_structured_return(self) -> None:
        # D17 regression: dicts must NOT become "{'foo': 1}".
        record = CapturedOutput(tool_name="t", return_value={"foo": 1, "bar": [2, 3]})
        d = record.as_dict()
        assert d["return_value"] == {"foo": 1, "bar": [2, 3]}


class TestOutputCapture:
    """OutputCapture accumulates execution records."""

    def test_record_success(self) -> None:
        capture = OutputCapture()
        record = capture.record_success("echo", {"text": "hi"}, result="hi")
        assert record.succeeded is True
        assert len(capture.history) == 1

    def test_record_failure(self) -> None:
        capture = OutputCapture()
        exc = RuntimeError("boom")
        record = capture.record_failure("bad_tool", {}, exc)
        assert record.succeeded is False
        assert "boom" in (record.error or "")

    def test_clear(self) -> None:
        capture = OutputCapture()
        capture.record_success("a", {})
        capture.record_success("b", {})
        assert len(capture.history) == 2
        capture.clear()
        assert len(capture.history) == 0
