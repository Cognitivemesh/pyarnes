"""Persistent graph storage — JSON node-link format on disk."""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx

from pyarnes_core.atomic_write import write_private

__all__ = ["load_graph", "save_graph"]


def save_graph(graph: nx.DiGraph, path: Path) -> None:
    """Atomically write *graph* to *path* as networkx node-link JSON.

    The 0o600 + atomic-rename guarantees from
    :func:`pyarnes_core.atomic_write.write_private` mean a crash mid-write
    leaves the previous graph file intact; readers never see a partial JSON.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = nx.node_link_data(graph, edges="edges")
    write_private(path, json.dumps(payload, default=str, indent=2))


def load_graph(path: Path) -> nx.DiGraph:
    """Load a graph previously written by :func:`save_graph`."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return nx.node_link_graph(payload, directed=True, edges="edges")
