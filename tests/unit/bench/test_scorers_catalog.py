"""Tests for the trajectory scorers (ToolUse / TrajectoryLength / GuardrailCompliance)."""

from __future__ import annotations

import json
from pathlib import Path

from pyarnes_bench import (
    GuardrailComplianceScorer,
    ToolUseCorrectnessScorer,
    TrajectoryLengthScorer,
)
from pyarnes_harness import ToolCallEntry, read_cc_session

FIXTURE = Path(__file__).parent.parent / "fixtures" / "cc_session_sample.jsonl"


def _entry(tool: str, *, is_error: bool = False) -> ToolCallEntry:
    return ToolCallEntry(
        tool=tool,
        arguments={},
        result="ok",
        is_error=is_error,
        started_at="2026-04-21T10:00:00Z",
        finished_at="2026-04-21T10:00:00Z",
        duration_seconds=0.0,
    )


class TestToolUseCorrectnessScorer:
    """LCS ratio between expected tool names and observed ToolCallEntry sequence."""

    def test_exact_match(self) -> None:
        s = ToolUseCorrectnessScorer()
        assert s.score(["Read", "Bash"], [_entry("Read"), _entry("Bash")]) == 1.0

    def test_out_of_order_partial(self) -> None:
        s = ToolUseCorrectnessScorer()
        # expected [R, B] vs observed [B, R] — LCS = 1 → 0.5
        assert s.score(["Read", "Bash"], [_entry("Bash"), _entry("Read")]) == 0.5

    def test_extra_calls_dont_lower(self) -> None:
        s = ToolUseCorrectnessScorer()
        observed = [_entry("Read"), _entry("Grep"), _entry("Bash")]
        assert s.score(["Read", "Bash"], observed) == 1.0

    def test_errors_ignored_by_default(self) -> None:
        s = ToolUseCorrectnessScorer()
        observed = [_entry("Read", is_error=True), _entry("Read"), _entry("Bash")]
        assert s.score(["Read", "Bash"], observed) == 1.0

    def test_empty_expected_no_observed(self) -> None:
        s = ToolUseCorrectnessScorer()
        assert s.score([], []) == 1.0

    def test_empty_expected_with_observed(self) -> None:
        s = ToolUseCorrectnessScorer()
        assert s.score([], [_entry("Read")]) == 0.0


class TestTrajectoryLengthScorer:
    """Length budget with linear decay beyond tolerance."""

    def test_in_tolerance_scores_one(self) -> None:
        s = TrajectoryLengthScorer(target_length=5, tolerance=2)
        entries = [_entry("X") for _ in range(5)]
        assert s.score(None, entries) == 1.0

    def test_edge_of_tolerance(self) -> None:
        s = TrajectoryLengthScorer(target_length=5, tolerance=2)
        entries = [_entry("X") for _ in range(7)]  # 7 = 5 + tolerance
        assert s.score(None, entries) == 1.0

    def test_past_tolerance_decays(self) -> None:
        s = TrajectoryLengthScorer(target_length=5, tolerance=2)
        entries = [_entry("X") for _ in range(8)]  # delta=3, excess=1, window=2 → 0.5
        assert s.score(None, entries) == 0.5

    def test_hits_zero(self) -> None:
        s = TrajectoryLengthScorer(target_length=5, tolerance=2)
        entries = [_entry("X") for _ in range(20)]
        assert s.score(None, entries) == 0.0

    def test_expected_int_overrides_target(self) -> None:
        s = TrajectoryLengthScorer(target_length=100, tolerance=0)
        entries = [_entry("X") for _ in range(3)]
        assert s.score(3, entries) == 1.0

    def test_errors_dont_count_toward_length(self) -> None:
        s = TrajectoryLengthScorer(target_length=3, tolerance=0)
        entries = [_entry("X", is_error=True), _entry("X"), _entry("X"), _entry("X")]
        assert s.score(None, entries) == 1.0


class TestGuardrailComplianceScorer:
    """Compliance ratio from call count vs. sidecar violation log."""

    def test_no_calls_no_violations_is_one(self, tmp_path: Path) -> None:
        s = GuardrailComplianceScorer()
        assert s.score(tmp_path / "missing.jsonl", []) == 1.0

    def test_all_clean(self, tmp_path: Path) -> None:
        s = GuardrailComplianceScorer()
        log = tmp_path / "violations.jsonl"
        # missing file → 0 violations → 1.0
        assert s.score(log, [_entry("Read"), _entry("Bash")]) == 1.0

    def test_one_violation_among_four_calls(self, tmp_path: Path) -> None:
        log = tmp_path / "violations.jsonl"
        log.write_text(json.dumps({"guardrail": "X", "tool": "Bash", "reason": "r", "hook": "Pre"}) + "\n")
        s = GuardrailComplianceScorer()
        assert s.score(log, [_entry("Read") for _ in range(4)]) == 0.75

    def test_more_violations_than_calls_clamps_to_zero(self, tmp_path: Path) -> None:
        log = tmp_path / "violations.jsonl"
        log.write_text(
            "\n".join(json.dumps({"guardrail": "X", "tool": "Bash", "reason": "r", "hook": "Pre"}) for _ in range(5))
            + "\n"
        )
        s = GuardrailComplianceScorer()
        assert s.score(log, [_entry("Read")]) == 0.0

    def test_session_id_filter(self, tmp_path: Path) -> None:
        log = tmp_path / "violations.jsonl"
        log.write_text(
            "\n".join(
                [
                    json.dumps({"guardrail": "X", "tool": "Bash", "reason": "r", "hook": "Pre", "session_id": "a"}),
                    json.dumps({"guardrail": "X", "tool": "Bash", "reason": "r", "hook": "Pre", "session_id": "b"}),
                    json.dumps({"guardrail": "X", "tool": "Bash", "reason": "r", "hook": "Pre", "session_id": "a"}),
                ]
            )
            + "\n"
        )
        s = GuardrailComplianceScorer(session_id="a")
        # 2 violations for session a / 4 calls → 0.5
        assert s.score(log, [_entry("Read") for _ in range(4)]) == 0.5

    def test_malformed_lines_skipped(self, tmp_path: Path) -> None:
        log = tmp_path / "violations.jsonl"
        log.write_text(
            "\n".join(
                [
                    "not json",
                    json.dumps({"guardrail": "X", "tool": "Bash", "reason": "r", "hook": "Pre"}),
                    "",
                ]
            )
            + "\n"
        )
        s = GuardrailComplianceScorer()
        assert s.score(log, [_entry("Read") for _ in range(2)]) == 0.5


class TestScorersEndToEndWithCCTranscript:
    """Feed real CC session entries from the shipped fixture through the scorers."""

    def test_tool_use_correctness_against_fixture(self) -> None:
        entries = list(read_cc_session(FIXTURE))
        s = ToolUseCorrectnessScorer()
        # Fixture has [Bash (ok), Read (error)] — with ignore_errors, observed = [Bash]
        assert s.score(["Bash"], entries) == 1.0

    def test_length_scorer_against_fixture(self) -> None:
        entries = list(read_cc_session(FIXTURE))
        # Non-error calls = 1 (only Bash succeeded); target 1, tolerance 0 → 1.0
        s = TrajectoryLengthScorer(target_length=1, tolerance=0)
        assert s.score(None, entries) == 1.0

    def test_compliance_against_fixture_no_log(self, tmp_path: Path) -> None:
        entries = list(read_cc_session(FIXTURE))
        s = GuardrailComplianceScorer()
        assert s.score(tmp_path / "absent.jsonl", entries) == 1.0
