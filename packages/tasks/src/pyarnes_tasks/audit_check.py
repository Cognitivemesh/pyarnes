"""``tasks audit:check`` — run all detectors; non-zero exit on HIGH findings."""

from __future__ import annotations

import sys
from collections import defaultdict

from pyarnes_bench.audit import audit_graph, summarize
from pyarnes_tasks._audit_common import bootstrap, require_graph

_DISPLAY_LIMIT = 10  # max rows shown per category before "and N more" tail


def main() -> int:
    """Run all audit detectors against the persisted graph; return non-zero on HIGH findings."""
    ctx = bootstrap("tasks audit:check")
    graph = require_graph(ctx, "audit:check")
    if isinstance(graph, int):
        return graph

    findings = audit_graph(
        graph,
        config=ctx.config,
        logger=ctx.logger,
        session_id=ctx.session_id,
        trace_id=ctx.trace_id,
        step=0,
    )
    summary = summarize(findings)

    print("audit:check")  # noqa: T201
    print(f"  total findings: {summary.total}")  # noqa: T201
    print(f"  by severity   : {summary.by_severity}")  # noqa: T201
    print(f"  by category   : {summary.by_category}")  # noqa: T201

    # Group findings for readable output without losing the per-row detail.
    grouped: dict[str, list[str]] = defaultdict(list)
    for f in findings:
        line = f"[{f.severity:<6}] {f.target}"
        if f.detail:
            line += f"  {f.detail}"
        grouped[f.category].append(line)
    for category, rows in sorted(grouped.items()):
        print(f"\n  {category} ({len(rows)})")  # noqa: T201
        for row in rows[:_DISPLAY_LIMIT]:
            print(f"    {row}")  # noqa: T201
        if len(rows) > _DISPLAY_LIMIT:
            print(f"    ... and {len(rows) - _DISPLAY_LIMIT} more")  # noqa: T201

    return 1 if summary.has_high else 0


if __name__ == "__main__":
    sys.exit(main())
