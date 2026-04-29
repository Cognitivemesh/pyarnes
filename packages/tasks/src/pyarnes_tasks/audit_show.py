"""``tasks audit:show`` — load the persisted graph and print a summary."""

from __future__ import annotations

import sys
from collections import Counter

import networkx as nx

from pyarnes_core.observability import estimate_tokens
from pyarnes_tasks._audit_common import bootstrap, require_graph


def main() -> int:
    """Print a human-readable summary of the persisted audit graph."""
    ctx = bootstrap("tasks audit:show")
    graph = require_graph(ctx, "audit:show")
    if isinstance(graph, int):
        return graph

    kind_counts = Counter(attrs.get("kind", "?") for _, attrs in graph.nodes(data=True))
    edge_counts = Counter(attrs.get("kind", "?") for _, _, attrs in graph.edges(data=True))
    file_counts = Counter(attrs.get("file_path", "?") for _, attrs in graph.nodes(data=True))
    payload = nx.node_link_data(graph, edges="edges")
    token_estimate = estimate_tokens(payload)

    print("audit:show")  # noqa: T201
    print(f"  graph        : {ctx.config.graph_path}")  # noqa: T201
    print(f"  nodes        : {graph.number_of_nodes()}  edges: {graph.number_of_edges()}")  # noqa: T201
    print(f"  token estimate: {token_estimate}")  # noqa: T201
    print("  node kinds   :")  # noqa: T201
    for kind, count in kind_counts.most_common():
        print(f"    {kind:<10} {count}")  # noqa: T201
    print("  edge kinds   :")  # noqa: T201
    for kind, count in edge_counts.most_common():
        print(f"    {kind:<14} {count}")  # noqa: T201
    print("  busiest files:")  # noqa: T201
    for file_path, count in file_counts.most_common(5):
        print(f"    {count:>4}  {file_path}")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
