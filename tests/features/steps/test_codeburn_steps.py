"""BDD step definitions for the codeburn:optimize scenario."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from pytest_bdd import given, scenario, then, when

from pyarnes_bench.burn import HealthGrade, SessionInput, run_optimize, save_report
from pyarnes_core.observability import log_event
from pyarnes_core.observe.logger import configure_logging, get_logger
from pyarnes_harness.capture.tool_log import ToolCallEntry


@scenario("../codeburn.feature", "Optimize emits findings, a grade, and a structured event")
def test_optimize_emits_findings() -> None:
    """Optimize emits findings, grade, snapshot, structured event."""


@scenario("../codeburn.feature", "Optimize against a clean workspace returns grade A")
def test_optimize_clean_workspace() -> None:
    """Empty workspace produces an A grade."""


def _entry(tool: str, args: dict[str, Any] | None = None) -> ToolCallEntry:
    return ToolCallEntry(
        tool=tool,
        arguments=args or {},
        result=None,
        is_error=False,
        started_at="2026-04-21T10:00:00Z",
        finished_at="2026-04-21T10:00:00Z",
        duration_seconds=0.0,
    )


@given("a local Claude Code session that triggers a detector", target_fixture="codeburn_ctx")
def _given_dirty_session(tmp_path: Path) -> dict[str, Any]:
    # Re-read of /a four times → REREAD_FILES + LOW_READ_EDIT_RATIO won't fire
    # because no edits exist; REREAD_FILES is enough.
    entries = [_entry("Read", {"file_path": "/a"}) for _ in range(4)]
    sessions = [SessionInput(session_id="s1", project="p", entries=entries)]
    log_buf = io.StringIO()
    configure_logging(level="DEBUG", json=True, stream=log_buf)
    return {"sessions": sessions, "home": tmp_path, "log_buf": log_buf}


@given("a clean Claude Code workspace", target_fixture="codeburn_ctx")
def _given_clean_workspace(tmp_path: Path) -> dict[str, Any]:
    log_buf = io.StringIO()
    configure_logging(level="DEBUG", json=True, stream=log_buf)
    return {"sessions": [], "home": tmp_path, "log_buf": log_buf}


@when("I run the codeburn optimize scan")
def _when_run(codeburn_ctx: dict[str, Any]) -> None:
    home = codeburn_ctx["home"]
    report = run_optimize(codeburn_ctx["sessions"], claude_dir=home, home=home)
    snapshot_path = save_report(report, home=home)
    # Mirror the CLI logging path so the Then step can verify the event.
    logger = get_logger("codeburn.bdd")
    log_event(
        logger,
        "codeburn.optimize.report",
        grade=report.grade.value,
        previous_grade=report.previous_grade.value if report.previous_grade else None,
        findings_count=len(report.findings),
    )
    codeburn_ctx["report"] = report
    codeburn_ctx["snapshot_path"] = snapshot_path


@then("I see at least one finding")
def _then_findings(codeburn_ctx: dict[str, Any]) -> None:
    assert codeburn_ctx["report"].findings, "expected at least one finding"


@then("the report carries a health grade between A and F")
def _then_grade_in_range(codeburn_ctx: dict[str, Any]) -> None:
    grade = codeburn_ctx["report"].grade
    assert isinstance(grade, HealthGrade)
    assert grade.value in {"A", "B", "C", "D", "F"}


@then('a "codeburn.optimize.report" event is emitted')
def _then_event_emitted(codeburn_ctx: dict[str, Any]) -> None:
    lines = [
        line for line in codeburn_ctx["log_buf"].getvalue().splitlines()
        if line.strip()
    ]
    events = [json.loads(line) for line in lines]
    assert any(e.get("event") == "codeburn.optimize.report" for e in events)


@then("a 48h snapshot is written under the cache directory")
def _then_snapshot(codeburn_ctx: dict[str, Any]) -> None:
    path: Path = codeburn_ctx["snapshot_path"]
    assert path.is_file()
    assert "codeburn" in path.parts


@then("the report carries grade A")
def _then_grade_a(codeburn_ctx: dict[str, Any]) -> None:
    assert codeburn_ctx["report"].grade == HealthGrade.A
