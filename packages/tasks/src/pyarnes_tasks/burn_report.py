"""``tasks burn:report`` — token cost report across AI coding sessions.

Reads session files via ``pyarnes_bench.burn`` (currently Claude Code
JSONL only) and renders a per-project token/cost summary to stdout.

Cost amounts are in whatever denomination the CostCalculator returns
(LiteLLM defaults to USD). Pass ``--currency EUR`` to *label* the output
in a different currency; apply your own FX rate to the cost separately —
this task does not do currency conversion.

Usage::

    uv run tasks burn:report
    uv run tasks burn:report -- --currency EUR
    uv run tasks burn:report -- --project pyarnes
    uv run tasks burn:report -- --base /custom/.claude/projects
    uv run tasks burn:report -- --format json
    uv run tasks burn:report -- --by-model
    uv run tasks burn:report -- --exclude internal-* --exclude scratch
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from collections.abc import Sequence
from decimal import Decimal
from functools import reduce
from pathlib import Path
from typing import Any


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="tasks burn:report",
        description="Token cost report across AI coding sessions.",
    )
    parser.add_argument(
        "--base",
        type=Path,
        default=None,
        help="Override the session root directory (default: provider default).",
    )
    parser.add_argument(
        "--project",
        default=None,
        help="Filter output to a single project directory name.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Glob patterns to drop from the output (repeatable).",
    )
    parser.add_argument(
        "--by-model",
        action="store_true",
        help="Group rows by (project, model_family) instead of project alone.",
    )
    parser.add_argument(
        "--currency",
        default="USD",
        help="ISO 4217 currency label for the cost column (default: USD).",
    )
    parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format: 'table' (default) or 'json'.",
    )
    return parser.parse_args(argv)


_WORKSPACE_DIRS = frozenset(
    {
        "GitHub",
        "GitLab",
        "Bitbucket",
        "repos",
        "projects",
        "code",
        "dev",
        "workspace",
        "src",
        "work",
    }
)


def short_name(project: str) -> str:
    """Decode an encoded project directory name to a human-readable slug.

    Claude Code encodes ``/Users/x/GitHub/my-app`` as ``-Users-x-GitHub-my-app``.
    We find the last known workspace directory and take everything after it,
    preserving hyphens that are part of the project name.
    Falls back to the last dash-segment for non-standard layouts.
    """
    parts = project.lstrip("-").split("-")
    for i in range(len(parts) - 1, 0, -1):
        if parts[i] in _WORKSPACE_DIRS:
            remainder = parts[i + 1 :]
            if remainder:
                return "-".join(remainder)
    return parts[-1] if parts else project


def _matches_any(slug: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch.fnmatchcase(slug, pat) for pat in patterns)


def _render_table(rows: list[dict[str, Any]], totals: dict[str, Any]) -> None:
    headers = list(totals.keys())
    all_rows = [*rows, totals]
    widths = [max(len(h), *(len(str(r[h])) for r in all_rows)) for h in headers]
    sep = "  "
    fmt = sep.join(f"{{:<{w}}}" for w in widths)
    divider = sep.join("-" * w for w in widths)
    print(fmt.format(*headers))  # noqa: T201
    print(divider)  # noqa: T201
    for row in rows:
        print(fmt.format(*[str(row[h]) for h in headers]))  # noqa: T201
    print(divider)  # noqa: T201
    print(fmt.format(*[str(totals[h]) for h in headers]))  # noqa: T201


def main() -> int:
    """Entry point — returns a process exit code."""
    args = _parse_args(sys.argv[1:])

    try:
        from pyarnes_bench.burn import BurnTracker, ClaudeCodeProvider, LiteLLMCostCalculator  # noqa: PLC0415
    except ImportError as exc:
        print(f"error: pyarnes-bench is not installed ({exc})", file=sys.stderr)  # noqa: T201
        return 1

    calculator = LiteLLMCostCalculator(currency=args.currency)
    provider = ClaudeCodeProvider()
    tracker = BurnTracker(provider, calculator=calculator)

    report = tracker.report(base=args.base)

    sessions_all = report.get(provider.tool_name, [])
    if args.project:
        sessions_all = [s for s in sessions_all if short_name(s.project) == args.project]
    if args.exclude:
        sessions_all = [s for s in sessions_all if not _matches_any(short_name(s.project), args.exclude)]

    if not sessions_all:
        print("No sessions found.", file=sys.stderr)  # noqa: T201
        return 0

    from pyarnes_bench.burn.types import TokenUsage  # noqa: PLC0415

    by_key: dict[tuple[str, ...], list[Any]] = {}
    for s in sessions_all:
        slug = short_name(s.project)
        key = (slug, s.metadata.model_family) if args.by_model else (slug,)
        by_key.setdefault(key, []).append(s)

    rows: list[dict[str, Any]] = []
    grand_usage = TokenUsage()
    grand_cost = Decimal(0)
    for key, sessions in sorted(by_key.items()):
        usage = reduce(lambda a, b: a + b.usage, sessions, TokenUsage())
        cost_total = sum(
            (s.cost.amount for s in sessions if s.cost is not None),
            Decimal(0),
        )
        grand_usage = grand_usage + usage
        grand_cost += cost_total
        row: dict[str, Any] = {"project": key[0]}
        if args.by_model:
            row["model_family"] = key[1] or "(unknown)"
        row.update(
            {
                "sessions": len(sessions),
                "input": f"{usage.input_tokens:,}",
                "output": f"{usage.output_tokens:,}",
                "cache-create": f"{usage.cache_creation_tokens:,}",
                "cache-read": f"{usage.cache_read_tokens:,}",
                "cost": f"{cost_total:.4f} {args.currency}",
            }
        )
        rows.append(row)

    totals: dict[str, Any] = {"project": "TOTAL"}
    if args.by_model:
        totals["model_family"] = ""
    totals.update(
        {
            "sessions": str(len(sessions_all)),
            "input": f"{grand_usage.input_tokens:,}",
            "output": f"{grand_usage.output_tokens:,}",
            "cache-create": f"{grand_usage.cache_creation_tokens:,}",
            "cache-read": f"{grand_usage.cache_read_tokens:,}",
            "cost": f"{grand_cost:.4f} {args.currency}",
        }
    )

    if args.format == "json":
        payload = {
            "provider": provider.tool_name,
            "currency": args.currency,
            "projects": rows,
            "totals": totals,
        }
        print(json.dumps(payload, indent=2))  # noqa: T201
        return 0

    print(f"\nProvider: {provider.tool_name}  |  Sessions: {len(sessions_all)}  |  Currency: {args.currency}\n")  # noqa: T201
    _render_table(rows, totals)
    print()  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
