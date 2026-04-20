"""Tests for safety.molecules.sandbox_check."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyarnes_core.errors import UserFixableError
from pyarnes_core.safety import assert_within_roots


class TestAssertWithinRoots:
    """Composition of has_traversal + canonicalize + is_within_roots."""

    def test_allowed_path(self, tmp_path: Path) -> None:
        (tmp_path / "ok.py").touch()
        resolved = assert_within_roots(tmp_path / "ok.py", [tmp_path])
        assert resolved == (tmp_path / "ok.py").resolve()

    def test_traversal_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(UserFixableError, match="traversal"):
            assert_within_roots(str(tmp_path / ".." / "etc"), [tmp_path])

    def test_outside_root_rejected(self, tmp_path: Path) -> None:
        root = tmp_path / "workspace"
        root.mkdir()
        outside = tmp_path / "etc"
        with pytest.raises(UserFixableError, match="outside allowed roots"):
            assert_within_roots(outside, [root])

    def test_sibling_with_shared_prefix_rejected(self, tmp_path: Path) -> None:
        """/workspace_evil must not match /workspace."""
        root = tmp_path / "workspace"
        root.mkdir()
        evil = tmp_path / "workspace_evil"
        evil.mkdir()
        with pytest.raises(UserFixableError, match="outside allowed roots"):
            assert_within_roots(evil / "x", [root])

    def test_nul_byte_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(UserFixableError, match="traversal"):
            assert_within_roots("\x00/etc", [tmp_path])
