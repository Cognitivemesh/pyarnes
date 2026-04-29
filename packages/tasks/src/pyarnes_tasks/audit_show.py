"""``tasks audit:show`` — load the persisted graph and print a summary."""

from __future__ import annotations

import sys
from collections import Counter

import networkx as nx

from pyarnes_bench.audit import load_graph
from pyarnes_core.observability import estimate_tokens
from pyarnes_tasks._audit_common import bootstrap


def main() -> int:
    """Entry point for ``uv run tasks audit:show``."""
    ctx = bootstrap("tasks audit:show")
    graph_path = ctx.config.graph_path
    if not graph_path.is_file():
        print(  # noqa: T201
            f"audit:show  graph file not found at {graph_path}; run `tasks audit:build` first.",
            file=sys.stderr,
        )
        return 1

    graph = load_graph(graph_path)
    kind_counts = Counter(attrs.get("kind", "?") for _, attrs in graph.nodes(data=True))
    edge_counts = Counter(attrs.get("kind", "?") for _, _, attrs in graph.edges(data=True))
    file_counts = Counter(attrs.get("file_path", "?") for _, attrs in graph.nodes(data=True))
    payload = nx.node_link_data(graph, edges="edges")
    token_estimate = estimate_tokens(payload)

    print("audit:show")  # noqa: T201
    print(f"  graph        : {graph_path}")  # noqa: T201
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
