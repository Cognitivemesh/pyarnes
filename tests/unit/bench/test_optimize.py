"""Tests for the optimize layer — detectors, grade, snapshot helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pyarnes_bench.burn.optimize import (
    Finding,
    HealthGrade,
    SessionInput,
    compute_grade,
    detect_bloated_claude_md,
    detect_cache_creation_overhead,
    detect_ghost_agents_skills,
    detect_low_read_edit_ratio,
    detect_rereads,
    detect_uncapped_bash,
    detect_unused_mcp,
    save_report,
    snapshot_dir,
)
from pyarnes_core.errors import Severity
from pyarnes_harness.capture.tool_log import ToolCallEntry


def _e(
    tool: str,
    args: dict[str, Any] | None = None,
    *,
    is_error: bool = False,
    result: Any = None,
) -> ToolCallEntry:
    return ToolCallEntry(
        tool=tool,
        arguments=args or {},
        result=result,
        is_error=is_error,
        started_at="2026-04-21T10:00:00Z",
        finished_at="2026-04-21T10:00:00Z",
        duration_seconds=0.0,
    )


def _session(entries: list[ToolCallEntry], sid: str = "s1") -> SessionInput:
    return SessionInput(session_id=sid, project="p", entries=entries)


# ── detectors ──────────────────────────────────────────────────────────────


class TestDetectRereads:
    def test_flags_files_read_too_many_times(self) -> None:
        entries = [_e("Read", {"file_path": "/a"}) for _ in range(5)]
        findings = detect_rereads([_session(entries)])
        assert findings
        assert findings[0].code == "REREAD_FILES"
        assert "/a" in findings[0].title

    def test_below_threshold_no_finding(self) -> None:
        entries = [_e("Read", {"file_path": "/a"}) for _ in range(2)]
        assert detect_rereads([_session(entries)]) == []


class TestDetectLowReadEditRatio:
    def test_flags_blind_edits(self) -> None:
        entries = [
            _e("Edit", {"file_path": "/a"}),
            _e("Edit", {"file_path": "/b"}),
            _e("Edit", {"file_path": "/c"}),
        ]
        findings = detect_low_read_edit_ratio([_session(entries)])
        assert findings
        assert findings[0].code == "LOW_READ_EDIT_RATIO"
        assert findings[0].severity == Severity.HIGH

    def test_balanced_no_finding(self) -> None:
        entries = [
            _e("Read", {"file_path": "/a"}),
            _e("Edit", {"file_path": "/a"}),
        ]
        assert detect_low_read_edit_ratio([_session(entries)]) == []


class TestDetectUncappedBash:
    def test_flags_oversize_output(self) -> None:
        big = "x" * 20_000
        entries = [_e("Bash", {"command": "find /"}, result=big)]
        findings = detect_uncapped_bash([_session(entries)])
        assert findings
        assert findings[0].code == "UNCAPPED_BASH"

    def test_small_output_no_finding(self) -> None:
        entries = [_e("Bash", {"command": "ls"}, result="a\nb\n")]
        assert detect_uncapped_bash([_session(entries)]) == []


class TestDetectUnusedMcp:
    def test_unused_server_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "settings.json").write_text(
            json.dumps({"mcpServers": {"github": {}, "slack": {}}}),
            encoding="utf-8",
        )
        entries = [_e("mcp__github__list_repos", {})]
        findings = detect_unused_mcp([_session(entries)], claude_dir=tmp_path)
        assert findings
        assert findings[0].code == "UNUSED_MCP"
        assert "slack" in findings[0].evidence

    def test_no_settings_no_finding(self, tmp_path: Path) -> None:
        assert detect_unused_mcp([], claude_dir=tmp_path) == []

    def test_all_used_no_finding(self, tmp_path: Path) -> None:
        (tmp_path / "settings.json").write_text(
            json.dumps({"mcpServers": {"github": {}}}),
            encoding="utf-8",
        )
        entries = [_e("mcp__github__op", {})]
        assert detect_unused_mcp([_session(entries)], claude_dir=tmp_path) == []


class TestDetectGhostAgentsSkills:
    def test_unused_agent_flagged(self, tmp_path: Path) -> None:
        agents = tmp_path / "agents"
        agents.mkdir()
        (agents / "Reviewer.md").write_text("# reviewer", encoding="utf-8")
        findings = detect_ghost_agents_skills([_session([])], claude_dir=tmp_path)
        assert any(f.code == "GHOST_AGENTS" for f in findings)

    def test_invoked_agent_not_flagged(self, tmp_path: Path) -> None:
        agents = tmp_path / "agents"
        agents.mkdir()
        (agents / "Reviewer.md").write_text("", encoding="utf-8")
        entries = [_e("Task", {"subagent_type": "Reviewer"})]
        findings = detect_ghost_agents_skills([_session(entries)], claude_dir=tmp_path)
        assert all(f.code != "GHOST_AGENTS" for f in findings)


class TestDetectBloatedClaudeMd:
    def test_oversize_file_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "CLAUDE.md").write_text("x" * 20_000, encoding="utf-8")
        findings = detect_bloated_claude_md([_session([])], claude_dir=tmp_path)
        assert findings
        assert findings[0].code == "BLOATED_CLAUDE_MD"

    def test_too_many_imports_flagged(self, tmp_path: Path) -> None:
        body = "\n".join(f"@import-{i}.md" for i in range(10))
        (tmp_path / "CLAUDE.md").write_text(body, encoding="utf-8")
        findings = detect_bloated_claude_md([_session([])], claude_dir=tmp_path)
        assert findings


class TestDetectCacheChurn:
    def test_long_session_without_reads_flagged(self) -> None:
        entries = [_e("Edit", {"file_path": f"/x{i}"}) for i in range(25)]
        findings = detect_cache_creation_overhead([_session(entries)])
        assert findings
        assert findings[0].code == "CACHE_CHURN"


# ── grade ──────────────────────────────────────────────────────────────────


class TestComputeGrade:
    def test_no_findings_is_a(self) -> None:
        assert compute_grade([]) == HealthGrade.A

    def test_single_low_is_b(self) -> None:
        f = Finding(code="X", severity=Severity.LOW, title="t", detail="d")
        assert compute_grade([f]) == HealthGrade.B

    def test_medium_is_b_or_c(self) -> None:
        f = Finding(code="X", severity=Severity.MEDIUM, title="t", detail="d")
        # one MEDIUM (3) → B
        assert compute_grade([f]) == HealthGrade.B
        # two MEDIUM (6) → C
        assert compute_grade([f, f]) == HealthGrade.C

    def test_high_severity_pushes_to_d_or_f(self) -> None:
        h = Finding(code="X", severity=Severity.HIGH, title="t", detail="d")
        # two HIGH (14) → D
        assert compute_grade([h, h]) == HealthGrade.D
        # three HIGH (21) → F
        assert compute_grade([h, h, h]) == HealthGrade.F


# ── snapshot ────────────────────────────────────────────────────────────────


class TestSnapshot:
    def test_save_and_dir(self, tmp_path: Path) -> None:
        from pyarnes_bench.burn.optimize import OptimizeReport  # noqa: PLC0415

        report = OptimizeReport(
            findings=[],
            grade=HealthGrade.A,
            previous_grade=None,
            delta_48h={},
            generated_at="2026-04-21T10:00:00+00:00",
        )
        path = save_report(report, home=tmp_path)
        assert path.is_file()
        assert path.parent == snapshot_dir(home=tmp_path)
        # File mode is 0o600 — owner read/write only.
        assert path.stat().st_mode & 0o777 == 0o600
        body = json.loads(path.read_text(encoding="utf-8"))
        assert body["grade"] == "A"
