"""Tests for safety.atoms.arg_walker."""

from __future__ import annotations

from pyarnes_core.safety import walk_strings, walk_values_for_keys


class TestWalkStrings:
    """walk_strings yields every str reachable through dict/list/tuple."""

    def test_plain_string(self) -> None:
        assert list(walk_strings("hello")) == ["hello"]

    def test_list_of_strings(self) -> None:
        assert list(walk_strings(["a", "b", "c"])) == ["a", "b", "c"]

    def test_nested_dict(self) -> None:
        value = {"outer": {"inner": "deep"}}
        assert list(walk_strings(value)) == ["deep"]

    def test_mixed_types_ignored(self) -> None:
        value = {"a": 1, "b": "keep", "c": None, "d": b"bytes", "e": 2.5}
        assert list(walk_strings(value)) == ["keep"]

    def test_tuple_walked(self) -> None:
        assert list(walk_strings(("x", "y"))) == ["x", "y"]

    def test_max_depth_bounded(self) -> None:
        """Depth 0 on a container yields nothing; depth 1 reaches one level."""
        deep = {"a": {"b": {"c": "leaf"}}}
        assert list(walk_strings(deep, max_depth=0)) == []
        assert list(walk_strings(deep, max_depth=1)) == []

    def test_non_container_non_string_ignored(self) -> None:
        assert list(walk_strings(42)) == []


class TestWalkValuesForKeys:
    """walk_values_for_keys finds values at any nesting depth."""

    def test_top_level_key(self) -> None:
        values = list(walk_values_for_keys({"path": "/a"}, keys=("path",)))
        assert values == ["/a"]

    def test_nested_key(self) -> None:
        args = {"opts": {"path": "/etc/passwd"}}
        assert list(walk_values_for_keys(args, keys=("path",))) == ["/etc/passwd"]

    def test_list_value(self) -> None:
        args = {"paths": ["/a", "/b"]}
        values = list(walk_values_for_keys(args, keys=("paths",)))
        assert values == [["/a", "/b"]]

    def test_multiple_keys(self) -> None:
        args = {"source": "/a", "dest": "/b", "other": "x"}
        values = sorted(walk_values_for_keys(args, keys=("source", "dest")))
        assert values == ["/a", "/b"]

    def test_nested_in_list(self) -> None:
        args = {"items": [{"path": "/a"}, {"path": "/b"}]}
        values = list(walk_values_for_keys(args, keys=("path",)))
        assert values == ["/a", "/b"]
