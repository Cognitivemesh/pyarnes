"""Tests for the Claude Code session-JSONL adapter.

Locks the parser against the real-shape fixture in
``tests/unit/fixtures/cc_session_sample.jsonl`` so schema drift shows
up as a failing test rather than a silently wrong scorer.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from pyarnes_harness import read_cc_session, resolve_cc_session_path
from pyarnes_harness.capture.cc_session import MAX_TRANSCRIPT_LINE_BYTES
from pyarnes_harness.capture.tool_log import ToolCallEntry

FIXTURE = Path(__file__).parent / "fixtures" / "cc_session_sample.jsonl"


class TestReadCCSession:
    """Parse the shipped fixture into ToolCallEntry records."""

    def test_yields_two_tool_calls(self) -> None:
        entries = list(read_cc_session(FIXTURE))
        assert len(entries) == 2

    def test_first_call_pairs_with_successful_result(self) -> None:
        entries = list(read_cc_session(FIXTURE))
        first = entries[0]
        assert isinstance(first, ToolCallEntry)
        assert first.tool == "Bash"
        assert first.arguments == {"command": "rg -l Makefile"}
        assert first.is_error is False
        assert first.result == "Makefile\n"
        assert first.token_in == 120
        assert first.token_out == 40
        assert first.model == "claude-sonnet-4-6"

    def test_second_call_surfaces_error(self) -> None:
        entries = list(read_cc_session(FIXTURE))
        second = entries[1]
        assert second.tool == "Read"
        assert second.is_error is True
        assert second.result == "ENOENT: no such file"

    def test_text_only_assistant_emits_no_entries(self, tmp_path: Path) -> None:
        transcript = tmp_path / "t.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "type": "assistant",
                    "timestamp": "2026-04-21T10:00:00Z",
                    "message": {
                        "model": "claude-sonnet-4-6",
                        "content": [{"type": "text", "text": "hello"}],
                    },
                }
            )
            + "\n"
        )
        assert list(read_cc_session(transcript)) == []

    def test_tool_use_without_result_yields_none_result(self, tmp_path: Path) -> None:
        transcript = tmp_path / "t.jsonl"
        lines = [
            {
                "type": "assistant",
                "timestamp": "2026-04-21T10:00:00Z",
                "message": {
                    "model": "claude-sonnet-4-6",
                    "content": [
                        {"type": "tool_use", "id": "toolu_x", "name": "Bash", "input": {"command": "ls"}}
                    ],
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                },
            },
        ]
        transcript.write_text("\n".join(json.dumps(ln) for ln in lines) + "\n")
        entries = list(read_cc_session(transcript))
        assert len(entries) == 1
        assert entries[0].result is None
        assert entries[0].is_error is False

    def test_missing_usage_leaves_tokens_none(self, tmp_path: Path) -> None:
        transcript = tmp_path / "t.jsonl"
        lines = [
            {
                "type": "assistant",
                "timestamp": "2026-04-21T10:00:00Z",
                "message": {
                    "content": [
                        {"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {"command": "ls"}}
                    ],
                },
            },
            {
                "type": "user",
                "timestamp": "2026-04-21T10:00:01Z",
                "message": {
                    "content": [
                        {"type": "tool_result", "tool_use_id": "toolu_1", "is_error": False, "content": "ok"}
                    ]
                },
            },
        ]
        transcript.write_text("\n".join(json.dumps(ln) for ln in lines) + "\n")
        entry = next(iter(read_cc_session(transcript)))
        assert entry.token_in is None
        assert entry.token_out is None
        assert entry.model is None

    def test_list_content_tool_result_is_stringified(self, tmp_path: Path) -> None:
        transcript = tmp_path / "t.jsonl"
        lines = [
            {
                "type": "assistant",
                "timestamp": "2026-04-21T10:00:00Z",
                "message": {
                    "content": [
                        {"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {"file_path": "/a"}}
                    ]
                },
            },
            {
                "type": "user",
                "timestamp": "2026-04-21T10:00:01Z",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_1",
                            "is_error": False,
                            "content": [{"type": "text", "text": "part1"}, {"type": "text", "text": "part2"}],
                        }
                    ]
                },
            },
        ]
        transcript.write_text("\n".join(json.dumps(ln) for ln in lines) + "\n")
        entry = next(iter(read_cc_session(transcript)))
        assert entry.result == "part1part2"

    def test_oversize_line_is_skipped(self, tmp_path: Path) -> None:
        # A single line larger than MAX_TRANSCRIPT_LINE_BYTES is dropped
        # silently — we refuse to feed an adversarial transcript into
        # json.loads.
        transcript = tmp_path / "t.jsonl"
        huge_assistant = {
            "type": "assistant",
            "timestamp": "2026-04-21T10:00:00Z",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_big",
                        "name": "Bash",
                        "input": {"command": "x" * (MAX_TRANSCRIPT_LINE_BYTES + 1)},
                    }
                ]
            },
        }
        normal_assistant = {
            "type": "assistant",
            "timestamp": "2026-04-21T10:00:01Z",
            "message": {
                "content": [
                    {"type": "tool_use", "id": "toolu_ok", "name": "Bash", "input": {"command": "ls"}}
                ]
            },
        }
        transcript.write_text(
            json.dumps(huge_assistant) + "\n" + json.dumps(normal_assistant) + "\n"
        )
        entries = list(read_cc_session(transcript))
        assert len(entries) == 1
        assert entries[0].tool == "Bash"
        assert entries[0].arguments == {"command": "ls"}

    def test_malformed_json_line_is_skipped(self, tmp_path: Path) -> None:
        transcript = tmp_path / "t.jsonl"
        transcript.write_text("{not json\n")
        # Should yield nothing, not crash.
        assert list(read_cc_session(transcript)) == []


class TestResolveCCSessionPath:
    """Build the per-project transcript path the way CC does."""

    def test_escapes_cwd_with_dashes(self, tmp_path: Path) -> None:
        home = tmp_path / "home"
        project_dir = home / ".claude" / "projects" / "-home-user-demo"
        project_dir.mkdir(parents=True)
        path = resolve_cc_session_path(
            cwd="/home/user/demo",
            session_id="abc123",
            home=home,
        )
        assert path == project_dir / "abc123.jsonl"

    def test_picks_newest_when_session_id_missing(self, tmp_path: Path) -> None:
        home = tmp_path / "home"
        project_dir = home / ".claude" / "projects" / "-home-user-demo"
        project_dir.mkdir(parents=True)
        older = project_dir / "old.jsonl"
        newer = project_dir / "new.jsonl"
        older.write_text("{}\n")
        newer.write_text("{}\n")
        os.utime(older, (1_000_000, 1_000_000))
        os.utime(newer, (2_000_000, 2_000_000))

        path = resolve_cc_session_path(cwd="/home/user/demo", home=home)
        assert path == newer

    def test_raises_when_no_transcripts_exist(self, tmp_path: Path) -> None:
        home = tmp_path / "home"
        project_dir = home / ".claude" / "projects" / "-home-user-demo"
        project_dir.mkdir(parents=True)
        with pytest.raises(FileNotFoundError, match="No Claude Code transcripts"):
            resolve_cc_session_path(cwd="/home/user/demo", home=home)
