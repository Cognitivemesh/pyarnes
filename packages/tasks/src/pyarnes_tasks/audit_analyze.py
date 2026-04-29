"""``tasks audit:analyze`` — god nodes, surprising connections, suggested questions."""

from __future__ import annotations

import sys

from pyarnes_bench.audit import (
    god_nodes,
    load_graph,
    log_audit_analyzed,
    suggested_questions,
    surprising_connections,
)
from pyarnes_tasks._audit_common import bootstrap


def main() -> int:
    """Entry point for ``uv run tasks audit:analyze``."""
    ctx = bootstrap("tasks audit:analyze")
    graph_path = ctx.config.graph_path
    if not graph_path.is_file():
        print(  # noqa: T201
            f"audit:analyze  graph file not found at {graph_path}; run `tasks audit:build` first.",
            file=sys.stderr,
        )
        return 1

    graph = load_graph(graph_path)
    gods = god_nodes(graph, top_n=10)
    surprises = surprising_connections(graph, top_n=10)
    questions = suggested_questions(graph, top_n=7)

    log_audit_analyzed(
        ctx.logger,
        "god_nodes",
        count=len(gods),
        session_id=ctx.session_id,
        trace_id=ctx.trace_id,
        step=0,
    )
    log_audit_analyzed(
        ctx.logger,
        "surprises",
        count=len(surprises),
        session_id=ctx.session_id,
        trace_id=ctx.trace_id,
        step=1,
    )
    log_audit_analyzed(
        ctx.logger,
        "questions",
        count=len(questions),
        session_id=ctx.session_id,
        trace_id=ctx.trace_id,
        step=2,
    )

    print("audit:analyze")  # noqa: T201
    print("  god nodes (top 10 by total degree):")  # noqa: T201
    for entry in gods:
        print(f"    {entry['total_degree']:>4}  {entry['kind']:<8} {entry['name']}")  # noqa: T201
    print("  surprising connections (cross-community):")  # noqa: T201
    for s in surprises:
        print(f"    {s['kind']:<13} {s['src']}  ->  {s['dst']}")  # noqa: T201
    print("  suggested questions:")  # noqa: T201
    for q in questions:
        print(f"    - {q}")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
