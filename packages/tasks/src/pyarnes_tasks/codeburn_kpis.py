"""``tasks codeburn:kpis`` — per-session KPIs across CC sessions.

Renders one row per (project, session) with the KPIs from
:func:`pyarnes_bench.burn.compute_session_kpis`.

Usage::

    uv run tasks codeburn:kpis
    uv run tasks codeburn:kpis -- --project pyarnes
    uv run tasks codeburn:kpis -- --format json
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from pyarnes_bench.burn import (
    LiteLLMCostCalculator,
    TokenUsage,
    compute_session_kpis,
)
from pyarnes_core.observability import log_event
from pyarnes_core.observe.logger import get_logger
from pyarnes_tasks._codeburn_common import (
    configure_codeburn_logging,
    filter_by_project,
    filter_excludes,
    load_sessions,
)
from pyarnes_tasks.burn_report import _render_table


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="tasks codeburn:kpis",
        description="Per-session KPIs across CC sessions.",
    )
    parser.add_argument("--base", type=Path, default=None, help="Override session root.")
    parser.add_argument("--project", default=None, help="Filter to a single project slug.")
    parser.add_argument("--exclude", action="append", default=[], help="Glob patterns to drop.")
    parser.add_argument("--currency", default="USD", help="ISO 4217 currency label.")
    parser.add_argument("--format", choices=["table", "json"], default="table")
    return parser.parse_args(argv)


def _session_cost(entries: Any, calculator: LiteLLMCostCalculator) -> tuple[Decimal, str]:
    inp = sum(e.token_in or 0 for e in entries)
    out = sum(e.token_out or 0 for e in entries)
    model = next((e.model for e in entries if e.model), "")
    cost = calculator.calculate(model, TokenUsage(input_tokens=inp, output_tokens=out))
    if cost is None:
        return Decimal(0), ""
    return cost.amount, cost.currency


def main() -> int:
    """Entry point — returns a process exit code."""
    args = _parse_args(sys.argv[1:])
    configure_codeburn_logging()
    logger = get_logger(__name__)

    sessions = filter_excludes(filter_by_project(load_sessions(args.base), args.project), args.exclude)
    if not sessions:
        print("No sessions found.", file=sys.stderr)  # noqa: T201
        return 0

    calculator = LiteLLMCostCalculator(currency=args.currency)
    rows: list[dict[str, Any]] = []
    grand_calls = 0
    grand_cost = Decimal(0)
    for s in sessions:
        amount, currency = _session_cost(s.entries, calculator)
        from pyarnes_bench.burn.types import Cost  # noqa: PLC0415

        cost = Cost(amount=amount, currency=currency or args.currency)
        kpis = compute_session_kpis(
            list(s.entries),
            session_id=s.session_id,
            project=s.project,
            cost=cost,
        )
        log_event(
            logger,
            "codeburn.kpis.computed",
            session_id=kpis.session_id,
            one_shot_rate=kpis.one_shot_rate,
            retry_loops=kpis.retry_loops,
            cache_hit_rate=kpis.cache_hit_rate,
            cost_total=str(kpis.cost_total),
        )
        grand_calls += kpis.total_calls
        grand_cost += kpis.cost_total
        rows.append({
            "project": s.project,
            "session": s.session_id[:12],
            "calls": kpis.total_calls,
            "tools": kpis.unique_tools,
            "one-shot": f"{kpis.one_shot_rate:.2f}",
            "retries": kpis.retry_loops,
            "cache-hit": f"{kpis.cache_hit_rate:.2f}",
            "r/e": f"{kpis.read_edit_ratio:.2f}",
            "cost": f"{kpis.cost_total:.4f} {args.currency}",
        })

    totals = {
        "project": "TOTAL",
        "session": "",
        "calls": str(grand_calls),
        "tools": "",
        "one-shot": "",
        "retries": "",
        "cache-hit": "",
        "r/e": "",
        "cost": f"{grand_cost:.4f} {args.currency}",
    }

    if args.format == "json":
        payload = {"currency": args.currency, "sessions": rows, "totals": totals}
        print(json.dumps(payload, indent=2))  # noqa: T201
        return 0

    print(f"\nSessions: {len(sessions)}  |  Currency: {args.currency}\n")  # noqa: T201
    _render_table(rows, totals)
    print()  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
