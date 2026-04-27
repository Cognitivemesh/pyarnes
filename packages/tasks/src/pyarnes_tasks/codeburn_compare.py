"""``tasks codeburn:compare`` — A/B compare two models on real sessions.

Splits the discovered sessions by ``ToolCallEntry.model`` and produces
a side-by-side :class:`pyarnes_bench.burn.ModelComparison`.

Usage::

    uv run tasks codeburn:compare -- --a claude-sonnet-4-6 --b claude-opus-4-7
    uv run tasks codeburn:compare -- --a model-a --b model-b --project pyarnes
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

from pyarnes_bench.burn import (
    Cost,
    LiteLLMCostCalculator,
    ModelComparison,
    SessionKpis,
    TokenUsage,
    compare_models,
    compute_session_kpis,
)
from pyarnes_core.observability import log_event
from pyarnes_core.observe.logger import get_logger
from pyarnes_harness.capture.tool_log import ToolCallEntry
from pyarnes_tasks._codeburn_common import (
    DiscoveredSession,
    configure_codeburn_logging,
    filter_by_project,
    filter_excludes,
    load_sessions,
)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="tasks codeburn:compare",
        description="A/B compare two models across CC sessions.",
    )
    parser.add_argument("--a", required=True, help="First model id (or alias).")
    parser.add_argument("--b", required=True, help="Second model id (or alias).")
    parser.add_argument("--base", type=Path, default=None, help="Override session root.")
    parser.add_argument("--project", default=None, help="Filter to a single project slug.")
    parser.add_argument("--exclude", action="append", default=[], help="Glob patterns to drop.")
    parser.add_argument("--currency", default="USD", help="ISO 4217 currency label.")
    parser.add_argument("--format", choices=["table", "json"], default="table")
    return parser.parse_args(argv)


def _dominant_model(entries: Sequence[ToolCallEntry]) -> str:
    """Return the model id used by most calls in a session."""
    counts: dict[str, int] = {}
    for e in entries:
        if e.model:
            counts[e.model] = counts.get(e.model, 0) + 1
    if not counts:
        return ""
    return max(counts.items(), key=lambda kv: kv[1])[0]


def _kpis_for_session(
    s: DiscoveredSession,
    *,
    calculator: LiteLLMCostCalculator,
    currency: str,
) -> tuple[str, SessionKpis]:
    inp = sum(e.token_in or 0 for e in s.entries)
    out = sum(e.token_out or 0 for e in s.entries)
    model = _dominant_model(s.entries)
    cost = calculator.calculate(model, TokenUsage(input_tokens=inp, output_tokens=out))
    cost_obj = cost if cost is not None else Cost(amount=Decimal(0), currency=currency)
    kpis = compute_session_kpis(
        list(s.entries),
        session_id=s.session_id,
        project=s.project,
        cost=cost_obj,
    )
    return model, kpis


def _render_comparison(comp: ModelComparison, currency: str) -> None:
    rows = [
        ("model",            comp.a.model,                          comp.b.model),
        ("sessions",         str(comp.a.sessions),                  str(comp.b.sessions)),
        ("calls",            str(comp.a.total_calls),               str(comp.b.total_calls)),
        ("avg one-shot",     f"{comp.a.avg_one_shot_rate:.2f}",     f"{comp.b.avg_one_shot_rate:.2f}"),
        ("retry loops",      str(comp.a.total_retry_loops),         str(comp.b.total_retry_loops)),
        ("avg cache-hit",    f"{comp.a.avg_cache_hit_rate:.2f}",    f"{comp.b.avg_cache_hit_rate:.2f}"),
        ("cost total",       f"{comp.a.cost_total:.4f} {currency}", f"{comp.b.cost_total:.4f} {currency}"),
        ("cost per call",    f"{comp.a.cost_per_call:.6f}",         f"{comp.b.cost_per_call:.6f}"),
    ]
    width = max(len(r[0]) for r in rows)
    cola = max(len(r[1]) for r in rows)
    colb = max(len(r[2]) for r in rows)
    fmt = f"  {{:<{width}}}    {{:<{cola}}}    {{:<{colb}}}"
    print(fmt.format("metric", "A", "B"))  # noqa: T201
    print(fmt.format("-" * width, "-" * cola, "-" * colb))  # noqa: T201
    for r in rows:
        print(fmt.format(*r))  # noqa: T201


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
    by_model: dict[str, list[SessionKpis]] = {}
    for s in sessions:
        model, kpis = _kpis_for_session(s, calculator=calculator, currency=args.currency)
        if not model:
            continue
        by_model.setdefault(model, []).append(kpis)

    comp = compare_models(args.a, args.b, by_model)
    log_event(
        logger,
        "codeburn.compare.completed",
        model_a=comp.a.model,
        model_b=comp.b.model,
        sessions_a=comp.a.sessions,
        sessions_b=comp.b.sessions,
    )

    if args.format == "json":
        payload = {"comparison": comp.as_dict(), "currency": args.currency}
        print(json.dumps(payload, indent=2))  # noqa: T201
        return 0

    print(f"\nComparison: {args.a} vs {args.b}  |  Currency: {args.currency}\n")  # noqa: T201
    _render_comparison(comp, args.currency)
    print()  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
