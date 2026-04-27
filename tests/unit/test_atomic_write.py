"""Adversarial tests for write_private / append_private.

The happy-path and permission tests live in test_hardening.py.
This file adds what test_hardening.py leaves out:
- write_private symlink behaviour (append_private is tested there; write_private is not)
- Concurrent thread-level appends to prove O_APPEND atomicity
"""

from __future__ import annotations

import asyncio
import stat
from pathlib import Path

import pytest

from pyarnes_core import append_private, write_private


class TestWritePrivateSymlink:
    """write_private replaces a symlink with a real file; never follows it."""

    def test_symlink_is_replaced_not_followed(self, tmp_path: Path) -> None:
        real = tmp_path / "real.json"
        real.write_text("untouched")
        link = tmp_path / "link.json"
        link.symlink_to(real)

        write_private(link, "new content")

        # The link is now a regular file, not a symlink.
        assert not link.is_symlink()
        assert link.read_text() == "new content"
        # The original target is unmodified.
        assert real.read_text() == "untouched"

    def test_symlink_replaced_file_has_0o600(self, tmp_path: Path) -> None:
        real = tmp_path / "real.json"
        real.write_text("")
        link = tmp_path / "link.json"
        link.symlink_to(real)

        write_private(link, "{}")

        mode = stat.S_IMODE(link.stat().st_mode)
        assert mode == 0o600, f"expected 0o600, got {oct(mode)}"


class TestAppendPrivateConcurrent:
    """append_private uses O_APPEND; concurrent writes must not lose lines."""

    @pytest.mark.asyncio
    async def test_concurrent_thread_appends_no_data_loss(self, tmp_path: Path) -> None:
        target = tmp_path / "concurrent.jsonl"
        n = 50

        async def append_one(i: int) -> None:
            # asyncio.to_thread gives OS-level thread concurrency so
            # O_APPEND atomicity is actually exercised.
            await asyncio.to_thread(append_private, target, f"line{i}\n")

        await asyncio.gather(*[append_one(i) for i in range(n)])

        lines = target.read_text().splitlines()
        assert len(lines) == n, f"expected {n} lines, got {len(lines)}"
        line_numbers = {int(line.replace("line", "")) for line in lines}
        assert line_numbers == set(range(n))

    @pytest.mark.asyncio
    async def test_concurrent_appends_preserve_newlines(self, tmp_path: Path) -> None:
        target = tmp_path / "newlines.jsonl"
        n = 20

        async def append_one(i: int) -> None:
            await asyncio.to_thread(append_private, target, f"{i}\n")

        await asyncio.gather(*[append_one(i) for i in range(n)])

        content = target.read_text()
        # Every line should end with \n; no partial writes should have merged lines.
        lines = content.splitlines()
        assert len(lines) == n
        # All lines should parse as integers in range.
        values = {int(line) for line in lines}
        assert values == set(range(n))
