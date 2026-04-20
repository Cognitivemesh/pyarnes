"""Tests for JSONL tool-call logger."""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from pyarnes_core.observability import monotonic_duration, start_timer
from pyarnes_core.types import ModelClient, ToolHandler
from pyarnes_harness.capture.tool_log import ToolCallEntry, ToolCallLogger
from pyarnes_harness.loop import AgentLoop, LoopConfig


class TestToolCallEntry:
    """ToolCallEntry is an immutable record with dict serialisation."""

    def test_as_dict(self) -> None:
        entry = ToolCallEntry(
            tool="echo",
            arguments={"text": "hi"},
            result="hi",
            is_error=False,
            started_at="2026-01-01T00:00:00+00:00",
            finished_at="2026-01-01T00:00:01+00:00",
            duration_seconds=1.0,
        )
        d = entry.as_dict()
        assert d["tool"] == "echo"
        assert d["arguments"] == {"text": "hi"}
        assert d["result"] == "hi"
        assert d["is_error"] is False
        assert d["started_at"] == "2026-01-01T00:00:00+00:00"
        assert d["finished_at"] == "2026-01-01T00:00:01+00:00"
        assert d["duration_seconds"] == 1.0

    def test_frozen(self) -> None:
        entry = ToolCallEntry(
            tool="x",
            arguments={},
            result="",
            is_error=False,
            started_at="",
            finished_at="",
            duration_seconds=0.0,
        )
        with contextlib.suppress(AttributeError):
            entry.tool = "y"  # type: ignore[misc]


class TestToolCallLogger:
    """ToolCallLogger writes JSONL to disk."""

    def test_log_call_writes_jsonl(self, tmp_path: Path) -> None:
        log_file = tmp_path / "calls.jsonl"
        with ToolCallLogger(path=log_file) as log:
            entry = log.log_call(
                "read_file",
                {"path": "/workspace/a.py"},
                result="contents",
            )
        assert entry.tool == "read_file"
        assert entry.is_error is False

        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["tool"] == "read_file"
        assert data["arguments"] == {"path": "/workspace/a.py"}
        assert data["result"] == "contents"
        assert data["is_error"] is False
        assert "started_at" in data
        assert "finished_at" in data
        assert "duration_seconds" in data

    def test_log_error_call(self, tmp_path: Path) -> None:
        log_file = tmp_path / "calls.jsonl"
        with ToolCallLogger(path=log_file) as log:
            entry = log.log_call(
                "bad_tool",
                {"arg": 1},
                result="boom",
                is_error=True,
            )
        assert entry.is_error is True
        data = json.loads(log_file.read_text().strip())
        assert data["is_error"] is True
        assert data["result"] == "boom"

    def test_multiple_calls_append(self, tmp_path: Path) -> None:
        log_file = tmp_path / "calls.jsonl"
        with ToolCallLogger(path=log_file) as log:
            log.log_call("a", {}, result="1")
            log.log_call("b", {}, result="2")
            log.log_call("c", {}, result="3")
        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 3
        assert json.loads(lines[0])["tool"] == "a"
        assert json.loads(lines[1])["tool"] == "b"
        assert json.loads(lines[2])["tool"] == "c"

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        deep_path = tmp_path / "a" / "b" / "c" / "calls.jsonl"
        with ToolCallLogger(path=deep_path) as log:
            log.log_call("echo", {"text": "hi"}, result="hi")
        assert deep_path.exists()

    def test_custom_timestamps(self, tmp_path: Path) -> None:
        log_file = tmp_path / "calls.jsonl"
        with ToolCallLogger(path=log_file) as log:
            log.log_call(
                "tool",
                {},
                result="ok",
                started_at="2026-01-01T00:00:00+00:00",
                finished_at="2026-01-01T00:00:05+00:00",
                duration_seconds=5.0,
            )
        data = json.loads(log_file.read_text().strip())
        assert data["started_at"] == "2026-01-01T00:00:00+00:00"
        assert data["finished_at"] == "2026-01-01T00:00:05+00:00"
        assert data["duration_seconds"] == 5.0

    def test_start_stop_timer(self) -> None:
        iso, mono = start_timer()
        assert isinstance(iso, str)
        assert isinstance(mono, float)
        finished_iso, duration = monotonic_duration(mono)
        assert isinstance(finished_iso, str)
        assert duration >= 0.0

    def test_repr(self, tmp_path: Path) -> None:
        log_file = tmp_path / "calls.jsonl"
        with ToolCallLogger(path=log_file) as log:
            r = repr(log)
        assert "ToolCallLogger" in r
        assert "calls.jsonl" in r

    def test_path_property(self, tmp_path: Path) -> None:
        log_file = tmp_path / "calls.jsonl"
        with ToolCallLogger(path=log_file) as log:
            assert log.path == log_file

    def test_structured_result_preserved(self, tmp_path: Path) -> None:
        """Dict/list results round-trip through JSON unchanged."""
        log_file = tmp_path / "calls.jsonl"
        with ToolCallLogger(path=log_file) as log:
            log.log_call("query", {}, result={"rows": [1, 2, 3]})
        data = json.loads(log_file.read_text().strip())
        assert data["result"] == {"rows": [1, 2, 3]}

    def test_string_result_still_works(self, tmp_path: Path) -> None:
        log_file = tmp_path / "calls.jsonl"
        with ToolCallLogger(path=log_file) as log:
            log.log_call("echo", {}, result="hello")
        data = json.loads(log_file.read_text().strip())
        assert data["result"] == "hello"


# ── Helpers for loop integration tests ────────────────────────────────────


@dataclass
class _EchoTool(ToolHandler):
    """Tool that echoes its text argument."""

    async def execute(self, arguments: dict[str, Any]) -> Any:
        return arguments.get("text", "echo")


@dataclass
class _FakeModel(ModelClient):
    """Model returning a scripted action sequence."""

    actions: list[dict[str, Any]]
    _idx: int = 0

    async def next_action(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        action = self.actions[self._idx]
        self._idx += 1
        return action


class TestLoopWithToolCallLogger:
    """AgentLoop persists tool calls to JSONL when tool_call_logger is set."""

    @pytest.mark.asyncio()
    async def test_tool_call_logged_to_jsonl(self, tmp_path: Path) -> None:
        log_file = tmp_path / ".harness" / "tool_calls.jsonl"
        model = _FakeModel(
            actions=[
                {"type": "tool_call", "tool": "echo", "id": "c1", "arguments": {"text": "hello"}},
                {"type": "final_answer", "content": "done"},
            ]
        )
        tcl = ToolCallLogger(path=log_file)
        try:
            loop = AgentLoop(
                tools={"echo": _EchoTool()},
                model=model,
                config=LoopConfig(max_iterations=10),
                tool_call_logger=tcl,
            )
            await loop.run([])
        finally:
            tcl.close()

        assert log_file.exists()
        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["tool"] == "echo"
        assert data["arguments"] == {"text": "hello"}
        assert data["result"] == "hello"
        assert data["is_error"] is False
        assert "started_at" in data
        assert "finished_at" in data
        assert "duration_seconds" in data
