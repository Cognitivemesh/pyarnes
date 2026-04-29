"""Tests for ``pyarnes_bench.audit.schema``."""

from __future__ import annotations

from pyarnes_bench.audit.schema import Edge, EdgeKind, Node, NodeKind, make_node_id


def test_node_kind_values_are_human_readable() -> None:
    # The on-disk JSON should keep enum values as plain strings.
    assert str(NodeKind.MODULE) == "module"
    assert str(NodeKind.METHOD) == "method"


def test_edge_kind_values_are_human_readable() -> None:
    assert str(EdgeKind.IMPORTS_FROM) == "imports_from"
    assert str(EdgeKind.CALLS) == "calls"


def test_node_dataclass_round_trip() -> None:
    node = Node(
        id="path/to/x.py::pkg.X",
        kind=NodeKind.CLASS,
        name="X",
        file_path="path/to/x.py",
        line_start=1,
        line_end=10,
        qualname="pkg.X",
    )
    assert node.id == "path/to/x.py::pkg.X"
    assert node.extra == {}


def test_make_node_id_is_deterministic() -> None:
    assert make_node_id("a/b.py", "pkg.foo") == "a/b.py::pkg.foo"
    assert make_node_id("a/b.py", "pkg.foo") == make_node_id("a/b.py", "pkg.foo")


def test_edge_dataclass_carries_line_and_extra() -> None:
    edge = Edge(src="m::a", dst="m::b", kind=EdgeKind.CALLS, file_path="m.py", line=42)
    assert edge.line == 42
    assert edge.extra == {}
