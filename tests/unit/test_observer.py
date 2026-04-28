"""Tests for observer:tail and observer:filter task modules."""

from __future__ import annotations

import json
import sys
import time

from pyarnes_tasks.observer_filter import _filter_lines, _parse_args
from pyarnes_tasks.observer_filter import main as filter_main
from pyarnes_tasks.observer_tail import _format_line
from pyarnes_tasks.observer_tail import main as tail_main

# ── Shared fixtures ──────────────────────────────────────────────────────────

_INFO_LINE = json.dumps(
    {"timestamp": "2026-01-01T00:00:00", "level": "info", "event": "loop.iteration", "iteration": 1}
)
_WARN_LINE = json.dumps(
    {"timestamp": "2026-01-01T00:00:01", "level": "warning", "event": "tool.transient_retry", "tool": "read_file"}
)
_SESSION_LINE = json.dumps(
    {"timestamp": "2026-01-01T00:00:02", "level": "info", "event": "lifecycle.transition", "session_id": "abc123"}
)


# ── observer_tail ────────────────────────────────────────────────────────────


class TestFormatLine:
    """_format_line produces a readable string from JSONL input."""

    def test_event_appears_in_output(self) -> None:
        out = _format_line(_INFO_LINE)
        assert "loop.iteration" in out

    def test_level_uppercased(self) -> None:
        out = _format_line(_INFO_LINE)
        assert "INFO" in out

    def test_extra_fields_appear(self) -> None:
        out = _format_line(_INFO_LINE)
        assert "iteration" in out

    def test_timestamp_appears(self) -> None:
        out = _format_line(_INFO_LINE)
        assert "2026-01-01" in out

    def test_invalid_json_passes_through(self) -> None:
        raw = "not json at all"
        out = _format_line(raw)
        assert out == raw

    def test_warning_level_coloured(self) -> None:
        out = _format_line(_WARN_LINE)
        # ANSI yellow escape for warning.
        assert "\033[33m" in out


class TestTailMain:
    """tail main() exit codes."""

    def test_missing_arg_returns_1(self, monkeypatch) -> None:
        monkeypatch.setattr(sys, "argv", ["observer_tail"])
        assert tail_main() == 1

    def test_nonexistent_file_returns_1(self, monkeypatch) -> None:
        monkeypatch.setattr(sys, "argv", ["observer_tail", "/no/such/file.jsonl"])
        assert tail_main() == 1

    def test_existing_file_prints_lines(self, tmp_path, monkeypatch, capsys) -> None:
        log_file = tmp_path / "events.jsonl"
        log_file.write_text(_INFO_LINE + "\n" + _WARN_LINE + "\n")
        monkeypatch.setattr(sys, "argv", ["observer_tail", str(log_file)])
        # Patch time.sleep so the follow loop exits immediately on KeyboardInterrupt.
        monkeypatch.setattr(time, "sleep", lambda _: (_ for _ in ()).throw(KeyboardInterrupt))
        assert tail_main() == 0
        out = capsys.readouterr().out
        assert "loop.iteration" in out
        assert "tool.transient_retry" in out


# ── observer_filter ──────────────────────────────────────────────────────────


class TestParseArgs:
    """_parse_args extracts flags and source from argv."""

    def test_no_flags_returns_source(self) -> None:
        event_pat, session_id, level, source = _parse_args(["my.jsonl"])
        assert source == "my.jsonl"
        assert event_pat == ""
        assert session_id == ""
        assert level == ""

    def test_event_flag(self) -> None:
        event_pat, _, _, _ = _parse_args(["--event", "loop.iter", "my.jsonl"])
        assert event_pat == "loop.iter"

    def test_session_flag(self) -> None:
        _, session_id, _, _ = _parse_args(["--session", "abc123", "my.jsonl"])
        assert session_id == "abc123"

    def test_level_flag(self) -> None:
        _, _, level, _ = _parse_args(["--level", "warning", "my.jsonl"])
        assert level == "warning"

    def test_defaults_source_to_dash(self) -> None:
        _, _, _, source = _parse_args(["--event", "x"])
        assert source == "-"


class TestFilterLines:
    """_filter_lines output matches only the correct lines."""

    def _lines(self) -> list[str]:
        return [_INFO_LINE + "\n", _WARN_LINE + "\n", _SESSION_LINE + "\n"]

    def test_no_filter_passes_all(self, capsys) -> None:
        _filter_lines(self._lines(), event_pat="", session_id="", level="")
        out = capsys.readouterr().out.strip().splitlines()
        assert len(out) == 3

    def test_event_filter_matches_substring(self, capsys) -> None:
        _filter_lines(self._lines(), event_pat="loop", session_id="", level="")
        out = capsys.readouterr().out.strip().splitlines()
        assert len(out) == 1
        assert "loop.iteration" in out[0]

    def test_event_filter_case_insensitive(self, capsys) -> None:
        _filter_lines(self._lines(), event_pat="LOOP", session_id="", level="")
        out = capsys.readouterr().out.strip().splitlines()
        assert len(out) == 1

    def test_session_filter_exact_match(self, capsys) -> None:
        _filter_lines(self._lines(), event_pat="", session_id="abc123", level="")
        out = capsys.readouterr().out.strip().splitlines()
        assert len(out) == 1
        assert "lifecycle.transition" in out[0]

    def test_level_filter(self, capsys) -> None:
        _filter_lines(self._lines(), event_pat="", session_id="", level="warning")
        out = capsys.readouterr().out.strip().splitlines()
        assert len(out) == 1
        assert "transient_retry" in out[0]

    def test_combined_filters_and_logic(self, capsys) -> None:
        # event=lifecycle AND session=abc123 → only SESSION_LINE matches.
        _filter_lines(self._lines(), event_pat="lifecycle", session_id="abc123", level="")
        out = capsys.readouterr().out.strip().splitlines()
        assert len(out) == 1

    def test_invalid_json_lines_skipped(self, capsys) -> None:
        _filter_lines(["not json\n", _INFO_LINE + "\n"], event_pat="", session_id="", level="")
        out = capsys.readouterr().out.strip().splitlines()
        assert len(out) == 1

    def test_empty_lines_skipped(self, capsys) -> None:
        _filter_lines(["\n", "  \n", _INFO_LINE + "\n"], event_pat="", session_id="", level="")
        out = capsys.readouterr().out.strip().splitlines()
        assert len(out) == 1


class TestFilterMain:
    """filter main() exit codes and file I/O."""

    def test_missing_arg_returns_1(self, monkeypatch) -> None:
        monkeypatch.setattr(sys, "argv", ["observer_filter"])
        assert filter_main() == 1

    def test_nonexistent_file_returns_1(self, monkeypatch) -> None:
        monkeypatch.setattr(sys, "argv", ["observer_filter", "/no/such/file.jsonl"])
        assert filter_main() == 1

    def test_file_filter_returns_0(self, tmp_path, monkeypatch, capsys) -> None:
        log_file = tmp_path / "events.jsonl"
        log_file.write_text(_INFO_LINE + "\n")
        monkeypatch.setattr(sys, "argv", ["observer_filter", str(log_file)])
        assert filter_main() == 0
        out = capsys.readouterr().out
        assert "loop.iteration" in out

    def test_event_flag_filters_correctly(self, tmp_path, monkeypatch, capsys) -> None:
        log_file = tmp_path / "events.jsonl"
        log_file.write_text(_INFO_LINE + "\n" + _WARN_LINE + "\n")
        monkeypatch.setattr(sys, "argv", ["observer_filter", "--event", "transient", str(log_file)])
        assert filter_main() == 0
        out = capsys.readouterr().out
        assert "transient_retry" in out
        assert "loop.iteration" not in out
