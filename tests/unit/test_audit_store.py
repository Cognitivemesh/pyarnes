"""Round-trip tests for ``pyarnes_bench.audit.store``."""

from __future__ import annotations

from pathlib import Path

import networkx as nx

from pyarnes_bench.audit.store import load_graph, save_graph


def test_save_load_round_trip(tmp_path: Path) -> None:
    graph: nx.DiGraph = nx.DiGraph()
    graph.add_node("a", kind="module", name="a", file_path="a.py", line_start=1, line_end=1)
    graph.add_node("b", kind="function", name="b", file_path="a.py", line_start=2, line_end=4)
    graph.add_edge("a", "b", kind="contains", file_path="a.py", line=2, extra={})

    target = tmp_path / "graph.json"
    save_graph(graph, target)
    assert target.is_file()

    loaded = load_graph(target)
    assert loaded.number_of_nodes() == 2
    assert loaded.number_of_edges() == 1
    assert loaded.nodes["b"]["kind"] == "function"
    assert loaded.edges["a", "b"]["kind"] == "contains"


def test_save_creates_parent_dirs(tmp_path: Path) -> None:
    graph: nx.DiGraph = nx.DiGraph()
    graph.add_node("a")
    target = tmp_path / "deep" / "nested" / "graph.json"
    save_graph(graph, target)
    assert target.is_file()
