"""Structural analyses — god nodes, surprising connections, suggested questions.

All implementations use only ``networkx`` stdlib algorithms; no ``graspologic``
dependency. Phase 2 may swap in Leiden behind ``[tool.pyarnes-audit].community``.
"""

from __future__ import annotations

from collections.abc import Iterable

import networkx as nx
from networkx.algorithms import community as nx_community

__all__ = ["god_nodes", "suggested_questions", "surprising_connections"]


_BETWEENNESS_SAMPLE_THRESHOLD = 5_000


def _real_nodes(graph: nx.DiGraph) -> list[str]:
    """Nodes that represent real code entities (not synthetic FILE markers)."""
    return [n for n, attrs in graph.nodes(data=True) if attrs.get("kind") != "file"]


def god_nodes(graph: nx.DiGraph, *, top_n: int = 10) -> list[dict[str, int | str]]:
    """Top-N nodes by combined in-degree + out-degree."""
    real = _real_nodes(graph)
    scored = [
        {
            "id": n,
            "name": graph.nodes[n].get("name", n),
            "kind": graph.nodes[n].get("kind", ""),
            "in_degree": graph.in_degree(n),
            "out_degree": graph.out_degree(n),
            "total_degree": graph.in_degree(n) + graph.out_degree(n),
        }
        for n in real
    ]
    scored.sort(key=lambda row: row["total_degree"], reverse=True)
    return scored[:top_n]


def _undirected_communities(graph: nx.DiGraph) -> list[set[str]]:
    if graph.number_of_nodes() == 0:
        return []
    return list(nx_community.greedy_modularity_communities(graph.to_undirected()))


def _node_community_map(communities: list[set[str]]) -> dict[str, int]:
    return {n: idx for idx, members in enumerate(communities) for n in members}


def surprising_connections(graph: nx.DiGraph, *, top_n: int = 10) -> list[dict[str, str | int]]:
    """Edges that bridge distinct communities — a proxy for unexpected coupling."""
    communities = _undirected_communities(graph)
    if len(communities) < 2:  # noqa: PLR2004  # need ≥2 communities to detect cross-community bridges
        return []
    membership = _node_community_map(communities)
    bridges: list[dict[str, str | int]] = []
    for src, dst, attrs in graph.edges(data=True):
        src_comm = membership.get(src)
        dst_comm = membership.get(dst)
        if src_comm is None or dst_comm is None or src_comm == dst_comm:
            continue
        bridges.append(
            {
                "src": src,
                "dst": dst,
                "kind": attrs.get("kind", ""),
                "src_community": src_comm,
                "dst_community": dst_comm,
            }
        )
    # Order so the result is deterministic across runs.
    bridges.sort(key=lambda row: (row["src_community"], row["dst_community"], row["src"], row["dst"]))
    return bridges[:top_n]


def _bridge_nodes(graph: nx.DiGraph, *, top_n: int) -> list[tuple[str, float]]:
    if graph.number_of_nodes() == 0:
        return []
    n_nodes = graph.number_of_nodes()
    if n_nodes > _BETWEENNESS_SAMPLE_THRESHOLD:
        scores = nx.betweenness_centrality(graph, k=min(500, n_nodes), seed=0)
    else:
        scores = nx.betweenness_centrality(graph)
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return ranked[:top_n]


def _isolated_components(graph: nx.DiGraph) -> Iterable[set[str]]:
    components = nx.weakly_connected_components(graph)
    for comp in components:
        if 1 <= len(comp) <= 2:  # noqa: PLR2004  # genuinely tiny — surface-able
            yield comp


def suggested_questions(graph: nx.DiGraph, *, top_n: int = 7) -> list[str]:
    """Generate review questions from bridge nodes, god nodes, and isolated components."""
    questions: list[str] = []

    for node, score in _bridge_nodes(graph, top_n=3):
        name = graph.nodes[node].get("name", node)
        if score > 0:
            questions.append(
                f"`{name}` sits on the highest-betweenness path (score {score:.3f}); is the coupling intentional?"
            )

    for entry in god_nodes(graph, top_n=3):
        questions.append(  # noqa: PERF401  # the loop reads better than a comprehension here
            f"`{entry['name']}` has total degree {entry['total_degree']} — is it a god object that should be split?"
        )

    isolated = list(_isolated_components(graph))
    if isolated:
        questions.append(
            f"{len(isolated)} weakly-connected components have <= 2 nodes; are they orphans that can be removed?"
        )

    return questions[:top_n]
