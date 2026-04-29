"""Node and edge dataclasses + enums.

The on-disk graph format is the JSON serialisation of a ``networkx.DiGraph``;
``StrEnum`` values keep node/edge kinds human-readable when the file is
inspected directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = ["Edge", "EdgeKind", "Node", "NodeKind", "make_node_id"]


class NodeKind(StrEnum):
    """High-level kinds of nodes the parser emits."""

    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    FILE = "file"


class EdgeKind(StrEnum):
    """High-level kinds of edges the parser emits."""

    CONTAINS = "contains"
    IMPORTS = "imports"
    IMPORTS_FROM = "imports_from"
    CALLS = "calls"
    INHERITS = "inherits"


@dataclass(frozen=True, slots=True)
class Node:
    """A node in the code graph."""

    id: str
    kind: NodeKind
    name: str
    file_path: str
    line_start: int
    line_end: int
    qualname: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Edge:
    """An edge between two nodes."""

    src: str
    dst: str
    kind: EdgeKind
    file_path: str
    line: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


def make_node_id(file_path: str, qualname: str) -> str:
    """Return the canonical node id for *qualname* in *file_path*.

    The same scheme is used by parser, builder, and detectors so cross-module
    references always resolve to the same key.
    """
    return f"{file_path}::{qualname}"
