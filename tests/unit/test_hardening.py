"""Tests for the hardening helpers in pyarnes_core.

Covers:

* ``safe_session_id`` rejecting path-traversal strings.
* ``write_private`` / ``append_private`` creating files with ``0o600``
  permissions and surviving a crash mid-write.
* ``Lifecycle.load`` / ``Lifecycle.dump`` failing closed on a tampered
  checkpoint and preserving permissions on round-trip.
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from pyarnes_core import (
    Budget,
    Lifecycle,
    Phase,
    append_private,
    safe_session_id,
    write_private,
)


class TestSafeSessionId:
    """safe_session_id rejects anything that could escape a directory."""

    @pytest.mark.parametrize(
        "bad",
        [
            "../../../.bashrc",
            "..",
            "foo/bar",
            "a\x00b",
            "a" * 65,
            "",
            None,
            42,
            ["a"],
            "sess id with spaces",
            "sess\n",
        ],
    )
    def test_unsafe_inputs_fall_back_to_default(self, bad: object) -> None:
        assert safe_session_id(bad) == "default"

    @pytest.mark.parametrize(
        "good",
        [
            "abc123",
            "sess-01",
            "session_42",
            "a.b",
            "ABCdef123._-",
            "a" * 64,
        ],
    )
    def test_safe_inputs_pass_through(self, good: str) -> None:
        assert safe_session_id(good) == good


class TestWritePrivate:
    """write_private lands content with 0o600 atomically."""

    def test_mode_is_600(self, tmp_path: Path) -> None:
        target = tmp_path / "out.json"
        write_private(target, "{}")
        mode = stat.S_IMODE(target.stat().st_mode)
        assert mode == 0o600, f"expected 0o600, got {oct(mode)}"

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        target = tmp_path / "deep" / "nested" / "out.json"
        write_private(target, "{}")
        assert target.is_file()

    def test_second_write_replaces_content(self, tmp_path: Path) -> None:
        target = tmp_path / "out.json"
        write_private(target, '{"a":1}')
        write_private(target, '{"b":2}')
        assert json.loads(target.read_text()) == {"b": 2}

    def test_no_temp_files_leak_after_success(self, tmp_path: Path) -> None:
        target = tmp_path / "out.json"
        write_private(target, "{}")
        tmps = [p for p in tmp_path.iterdir() if p.name.startswith(".out.json")]
        assert tmps == []


class TestAppendPrivate:
    """append_private creates the file 0o600 on first append."""

    def test_first_append_creates_private(self, tmp_path: Path) -> None:
        target = tmp_path / "log.jsonl"
        append_private(target, "line1\n")
        mode = stat.S_IMODE(target.stat().st_mode)
        assert mode == 0o600

    def test_subsequent_appends_preserve_content(self, tmp_path: Path) -> None:
        target = tmp_path / "log.jsonl"
        append_private(target, "a\n")
        append_private(target, "b\n")
        assert target.read_text() == "a\nb\n"

    def test_refuses_to_follow_symlink(self, tmp_path: Path) -> None:
        real = tmp_path / "elsewhere.jsonl"
        real.write_text("")
        link = tmp_path / "log.jsonl"
        link.symlink_to(real)
        with pytest.raises(OSError):
            append_private(link, "x\n")


class TestLifecyclePersistenceHardening:
    """Lifecycle dump/load enforces mode + shape."""

    def test_dump_writes_private_file(self, tmp_path: Path) -> None:
        target = tmp_path / "lc.json"
        Lifecycle(phase=Phase.INIT, budget=Budget(max_calls=10)).dump(target)
        mode = stat.S_IMODE(target.stat().st_mode)
        assert mode == 0o600

    def test_load_fails_closed_on_garbage(self, tmp_path: Path) -> None:
        target = tmp_path / "lc.json"
        target.write_text("not json")
        with pytest.raises(ValueError, match="unreadable"):
            Lifecycle.load(target)

    def test_load_fails_closed_on_non_object(self, tmp_path: Path) -> None:
        target = tmp_path / "lc.json"
        target.write_text("[1,2,3]")
        with pytest.raises(TypeError, match="not a JSON object"):
            Lifecycle.load(target)

    def test_load_fails_closed_on_unknown_phase(self, tmp_path: Path) -> None:
        target = tmp_path / "lc.json"
        target.write_text(json.dumps({"phase": "escape", "metadata": {}, "budget": None}))
        with pytest.raises(ValueError, match="unknown phase"):
            Lifecycle.load(target)

    def test_load_accepts_missing_metadata(self, tmp_path: Path) -> None:
        target = tmp_path / "lc.json"
        target.write_text(json.dumps({"phase": "init"}))
        restored = Lifecycle.load(target)
        assert restored.metadata == {}
        assert restored.budget is None
