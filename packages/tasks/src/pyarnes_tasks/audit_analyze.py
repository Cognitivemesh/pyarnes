"""``tasks audit:analyze`` — god nodes, surprising connections, suggested questions."""

from __future__ import annotations

import sys

from pyarnes_bench.audit import (
    god_nodes,
    log_audit_analyzed,
    suggested_questions,
    surprising_connections,
)
from pyarnes_tasks._audit_common import bootstrap, require_graph


def main() -> int:
    """Print god nodes, surprising connections, and suggested review questions."""
    ctx = bootstrap("tasks audit:analyze")
    graph = require_graph(ctx, "audit:analyze")
    if isinstance(graph, int):
        return graph

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
