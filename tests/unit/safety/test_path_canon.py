"""Tests for safety.atoms.path_canon."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyarnes_core.safety.atoms import canonicalize, has_traversal


class TestHasTraversal:
    """has_traversal flags .. segments and NUL bytes."""

    def test_plain_path_is_clean(self) -> None:
        assert has_traversal("/workspace/a/b") is False

    def test_double_dot_segment(self) -> None:
        assert has_traversal("/workspace/../etc/passwd") is True

    def test_nested_double_dot(self) -> None:
        assert has_traversal("/workspace/a/../../etc") is True

    def test_nul_byte_rejected(self) -> None:
        assert has_traversal("/workspace/\x00/etc") is True

    def test_path_object_accepted(self) -> None:
        assert has_traversal(Path("/workspace/../etc")) is True

    def test_relative_dot_not_flagged(self) -> None:
        """A single '.' is current-dir and normal; only '..' is rejected."""
        assert has_traversal("./foo") is False


class TestCanonicalize:
    """canonicalize collapses .. and returns absolute Path."""

    def test_collapses_double_dot(self, tmp_path: Path) -> None:
        candidate = tmp_path / "a" / ".." / "b"
        resolved = canonicalize(candidate)
        assert resolved == (tmp_path / "b").resolve()

    def test_returns_path_instance(self, tmp_path: Path) -> None:
        assert isinstance(canonicalize(tmp_path), Path)

    def test_nul_byte_raises(self) -> None:
        with pytest.raises(ValueError, match="NUL byte"):
            canonicalize("/workspace/\x00/x")

    def test_non_existent_path_resolves(self, tmp_path: Path) -> None:
        """strict=False lets missing paths still get normalized."""
        result = canonicalize(tmp_path / "does-not-exist")
        assert result.is_absolute()
