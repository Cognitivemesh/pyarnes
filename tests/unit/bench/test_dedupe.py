"""Tests for ``dedupe`` — drop replayed/duplicate calls from a CC stream."""

from __future__ import annotations

from typing import Any

from pyarnes_bench.burn.dedupe import dedupe
from pyarnes_harness.capture.tool_log import ToolCallEntry


def _entry(tool: str, args: dict[str, Any], ts: str = "2026-04-21T10:00:00Z") -> ToolCallEntry:
    return ToolCallEntry(
        tool=tool,
        arguments=args,
        result=None,
        is_error=False,
        started_at=ts,
        finished_at=ts,
        duration_seconds=0.0,
    )


class TestDedupe:
    def test_replay_collapses(self) -> None:
        a = _entry("Bash", {"command": "ls"}, ts="2026-04-21T10:00:00Z")
        b = _entry("Bash", {"command": "ls"}, ts="2026-04-21T10:00:00Z")
        result = list(dedupe([a, b]))
        assert len(result) == 1

    def test_distinct_timestamps_survive(self) -> None:
        a = _entry("Bash", {"command": "ls"}, ts="2026-04-21T10:00:00Z")
        b = _entry("Bash", {"command": "ls"}, ts="2026-04-21T10:00:01Z")
        result = list(dedupe([a, b]))
        assert len(result) == 2

    def test_distinct_args_survive(self) -> None:
        a = _entry("Bash", {"command": "ls"}, ts="2026-04-21T10:00:00Z")
        b = _entry("Bash", {"command": "pwd"}, ts="2026-04-21T10:00:00Z")
        result = list(dedupe([a, b]))
        assert len(result) == 2

    def test_normalised_tool_name_collapses_aliases(self) -> None:
        a = _entry("Bash", {"command": "x"}, ts="2026-04-21T10:00:00Z")
        b = _entry("bash", {"command": "x"}, ts="2026-04-21T10:00:00Z")
        result = list(dedupe([a, b]))
        assert len(result) == 1

    def test_preserves_order(self) -> None:
        a = _entry("Bash", {"command": "a"}, ts="2026-04-21T10:00:00Z")
        b = _entry("Bash", {"command": "b"}, ts="2026-04-21T10:00:01Z")
        c = _entry("Bash", {"command": "a"}, ts="2026-04-21T10:00:00Z")  # dup of a
        d = _entry("Bash", {"command": "c"}, ts="2026-04-21T10:00:02Z")
        result = list(dedupe([a, b, c, d]))
        assert [e.arguments["command"] for e in result] == ["a", "b", "c"]
