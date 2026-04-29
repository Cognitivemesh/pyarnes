"""``tasks audit:build`` — parse the project and persist the audit graph."""

from __future__ import annotations

import sys

from pyarnes_bench.audit import build_graph, save_graph
from pyarnes_tasks._audit_common import bootstrap


def main() -> int:
    ctx = bootstrap("tasks audit:build")
    graph = build_graph(
        config=ctx.config,
        logger=ctx.logger,
        session_id=ctx.session_id,
        trace_id=ctx.trace_id,
        step=0,
    )
    save_graph(graph, ctx.config.graph_path)
    print(  # noqa: T201
        f"audit:build  files={graph.graph.get('files', '?')}  "
        f"nodes={graph.number_of_nodes()}  edges={graph.number_of_edges()}  "
        f"-> {ctx.config.graph_path}",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
