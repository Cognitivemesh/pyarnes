"""``tasks codeburn:optimize`` — waste-detection scan with A-F grade.

Runs every detector in :func:`pyarnes_bench.burn.all_detectors`,
ranks the findings, computes the A-F :class:`HealthGrade`, persists a
48 h snapshot to ``~/.cache/pyarnes/codeburn/`` and renders the
result.

Usage::

    uv run tasks codeburn:optimize
    uv run tasks codeburn:optimize -- --format json
    uv run tasks codeburn:optimize -- --severity high --strict
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pyarnes_bench.burn import (
    Finding,
    HealthGrade,
    OptimizeReport,
    run_optimize,
    save_report,
)
from pyarnes_core.errors import Severity, UserFixableError
from pyarnes_core.observability import log_event, log_warning
from pyarnes_core.observe.logger import get_logger
from pyarnes_tasks._codeburn_common import (
    configure_codeburn_logging,
    filter_excludes,
    load_sessions,
    to_session_inputs,
)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="tasks codeburn:optimize",
        description="Waste-detection scan with A-F health grade.",
    )
    parser.add_argument("--base", type=Path, default=None, help="Override session root.")
    parser.add_argument("--exclude", action="append", default=[], help="Glob patterns to drop.")
    parser.add_argument(
        "--severity",
        choices=["low", "medium", "high", "critical"],
        default="low",
        help="Minimum severity to display (default: low).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when grade is D or F (CI use).",
    )
    parser.add_argument("--format", choices=["table", "json"], default="table")
    return parser.parse_args(argv)


def _grade_strict_fail(grade: HealthGrade) -> bool:
    return grade in {HealthGrade.D, HealthGrade.F}


def main() -> int:
    """Entry point — returns a process exit code."""
    args = _parse_args(sys.argv[1:])
    configure_codeburn_logging()
    logger = get_logger(__name__)

    try:
        sessions = filter_excludes(load_sessions(args.base), args.exclude)
    except UserFixableError as exc:
        log_warning(logger, "codeburn.session.unreadable", reason=str(exc))
        print(f"error: {exc}", file=sys.stderr)  # noqa: T201
        return 2

    inputs = to_session_inputs(sessions)
    report = run_optimize(inputs)

    for f in report.findings:
        log_event(
            logger,
            "codeburn.optimize.finding",
            code=f.code,
            severity=f.severity.value,
            est_tokens_saved=f.est_tokens_saved,
        )

    threshold = Severity(args.severity)
    visible = [f for f in report.findings if f.severity.weight >= threshold.weight]

    snapshot_path = save_report(report)
    log_event(
        logger,
        "codeburn.snapshot.written",
        path=str(snapshot_path),
        generated_at=report.generated_at,
    )
    log_event(
        logger,
        "codeburn.optimize.report",
        grade=report.grade.value,
        previous_grade=report.previous_grade.value if report.previous_grade else None,
        findings_count=len(report.findings),
        delta_48h=report.delta_48h,
    )

    if args.format == "json":
        payload = report.as_dict()
        payload["snapshot"] = str(snapshot_path)
        print(json.dumps(payload, indent=2))  # noqa: T201
    else:
        _render_text(report, visible, snapshot_path)

    return 1 if (args.strict and _grade_strict_fail(report.grade)) else 0


def _render_text(report: OptimizeReport, visible: list[Finding], snapshot_path: Path) -> None:
    grade = report.grade.value
    prev = report.previous_grade.value if report.previous_grade else "-"
    print(f"\nHealth grade: {grade}  |  previous (<=48h): {prev}")  # noqa: T201
    if report.delta_48h:
        delta = ", ".join(f"{k} {v:+d}" for k, v in report.delta_48h.items())
        print(f"Severity delta: {delta}")  # noqa: T201
    print(f"Snapshot: {snapshot_path}\n")  # noqa: T201
    if not visible:
        print("No findings at the requested severity.\n")  # noqa: T201
        return
    for f in visible:
        print(f"[{f.severity.value.upper()}] {f.code}: {f.title}")  # noqa: T201
        print(f"   {f.detail}")  # noqa: T201
        if f.fix:
            print(f"   fix: {f.fix}")  # noqa: T201
        if f.est_tokens_saved:
            print(f"   ~ {f.est_tokens_saved:,} tokens saved")  # noqa: T201
        print()  # noqa: T201


if __name__ == "__main__":
    sys.exit(main())
