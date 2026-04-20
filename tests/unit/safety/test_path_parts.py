"""Tests for safety.atoms.path_parts."""

from __future__ import annotations

from pathlib import Path

from pyarnes_core.safety import is_within_roots


class TestIsWithinRoots:
    """is_within_roots uses parts comparison, not string prefix."""

    def test_exact_match(self, tmp_path: Path) -> None:
        assert is_within_roots(tmp_path, [tmp_path]) is True

    def test_nested_path_allowed(self, tmp_path: Path) -> None:
        child = tmp_path / "a" / "b"
        assert is_within_roots(child, [tmp_path]) is True

    def test_sibling_with_shared_prefix_rejected(self, tmp_path: Path) -> None:
        """/workspace_evil must NOT match /workspace."""
        root = tmp_path / "workspace"
        root.mkdir()
        evil = tmp_path / "workspace_evil"
        evil.mkdir()
        assert is_within_roots(evil / "x", [root]) is False

    def test_traversal_collapses_out_of_root(self, tmp_path: Path) -> None:
        """``/workspace/../etc`` resolves outside the root."""
        root = tmp_path / "workspace"
        root.mkdir()
        outside = tmp_path / "etc"
        assert is_within_roots(root / ".." / "etc", [root]) is False
        assert is_within_roots(outside, [root]) is False

    def test_multiple_roots_any_match(self, tmp_path: Path) -> None:
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir()
        b.mkdir()
        assert is_within_roots(b / "x", [a, b]) is True

    def test_empty_roots_rejects_everything(self, tmp_path: Path) -> None:
        assert is_within_roots(tmp_path, []) is False
