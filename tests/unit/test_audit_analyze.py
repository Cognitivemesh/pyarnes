"""Tests for ``pyarnes_bench.audit.analyze``."""

from __future__ import annotations

import networkx as nx

from pyarnes_bench.audit.analyze import (
    god_nodes,
    suggested_questions,
    surprising_connections,
)


def _real(graph: nx.DiGraph, *names: str) -> None:
    for n in names:
        graph.add_node(n, kind="function", name=n)


def test_god_nodes_picks_highest_total_degree() -> None:
    g: nx.DiGraph = nx.DiGraph()
    _real(g, "a", "b", "c", "d")
    g.add_edge("a", "b", kind="calls")
    g.add_edge("a", "c", kind="calls")
    g.add_edge("a", "d", kind="calls")
    g.add_edge("b", "a", kind="calls")
    top = god_nodes(g, top_n=2)
    assert top[0]["name"] == "a"
    assert top[0]["total_degree"] == 4


def test_god_nodes_excludes_file_kind_nodes() -> None:
    g: nx.DiGraph = nx.DiGraph()
    g.add_node("file_node", kind="file", name="file_node")
    g.add_node("real", kind="function", name="real")
    g.add_edge("file_node", "real", kind="contains")
    top = god_nodes(g, top_n=5)
    assert all(entry["kind"] != "file" for entry in top)


def test_surprising_connections_returns_cross_community_edges() -> None:
    # Build two clusters that are loosely connected by a single bridge edge.
    g: nx.DiGraph = nx.DiGraph()
    cluster_a = ["a1", "a2", "a3"]
    cluster_b = ["b1", "b2", "b3"]
    for n in [*cluster_a, *cluster_b]:
        g.add_node(n, kind="function", name=n)
    for u in cluster_a:
        for v in cluster_a:
            if u != v:
                g.add_edge(u, v, kind="calls")
    for u in cluster_b:
        for v in cluster_b:
            if u != v:
                g.add_edge(u, v, kind="calls")
    g.add_edge("a1", "b1", kind="calls")  # the bridge

    surprises = surprising_connections(g, top_n=10)
    assert any({s["src"], s["dst"]} == {"a1", "b1"} for s in surprises)


def test_suggested_questions_returns_some_text() -> None:
    g: nx.DiGraph = nx.DiGraph()
    _real(g, "a", "b", "c", "orphan_x", "orphan_y")
    g.add_edge("a", "b", kind="calls")
    g.add_edge("b", "c", kind="calls")
    questions = suggested_questions(g, top_n=5)
    assert questions  # non-empty
    assert all(isinstance(q, str) for q in questions)
