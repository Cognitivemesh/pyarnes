"""Tests for session KPI computation."""

from __future__ import annotations

import io
import json
from decimal import Decimal
from typing import Any

from pyarnes_bench.burn.kpis import compute_session_kpis
from pyarnes_bench.burn.types import Cost
from pyarnes_core.observability import log_event
from pyarnes_core.observe.logger import configure_logging, get_logger
from pyarnes_harness.capture.tool_log import ToolCallEntry


def _e(tool: str, args: dict[str, Any] | None = None, *, is_error: bool = False) -> ToolCallEntry:
    return ToolCallEntry(
        tool=tool,
        arguments=args or {},
        result=None,
        is_error=is_error,
        started_at="2026-04-21T10:00:00Z",
        finished_at="2026-04-21T10:00:00Z",
        duration_seconds=0.0,
    )


class TestSessionKpis:
    def test_one_shot_rate_all_one_shot(self) -> None:
        # Single Edit followed by unrelated calls — counts as one-shot
        entries = [
            _e("Edit", {"file_path": "/a"}),
            _e("Read", {"file_path": "/b"}),
        ]
        k = compute_session_kpis(entries, session_id="s", project="p")
        assert k.one_shot_rate == 1.0

    def test_one_shot_rate_zero_when_followed_by_failing_test(self) -> None:
        entries = [
            _e("Edit", {"file_path": "/a"}),
            _e("Bash", {"command": "pytest"}, is_error=True),
        ]
        k = compute_session_kpis(entries, session_id="s", project="p")
        assert k.one_shot_rate == 0.0

    def test_one_shot_rate_zero_when_re_edited(self) -> None:
        entries = [
            _e("Edit", {"file_path": "/a"}),
            _e("Edit", {"file_path": "/a"}),
        ]
        k = compute_session_kpis(entries, session_id="s", project="p")
        # First edit is followed by re-edit on same path → not one-shot.
        # Second edit has no follower → one-shot.
        assert k.one_shot_rate == 0.5

    def test_retry_loops_counted(self) -> None:
        entries = [
            _e("Bash", {"command": "pytest"}, is_error=True),
            _e("Edit", {"file_path": "/a"}),
            _e("Bash", {"command": "pytest"}, is_error=False),
            _e("Bash", {"command": "pytest"}, is_error=True),
            _e("Edit", {"file_path": "/a"}),
            _e("Bash", {"command": "pytest"}, is_error=False),
        ]
        k = compute_session_kpis(entries, session_id="s", project="p")
        assert k.retry_loops == 2

    def test_cost_by_bucket_sums_to_total(self) -> None:
        entries = [
            _e("Edit", {"file_path": "/a"}),
            _e("Bash", {"command": "git status"}),
            _e("Bash", {"command": "pytest"}),
        ]
        k = compute_session_kpis(
            entries,
            session_id="s",
            project="p",
            cost=Cost(amount=Decimal("0.30"), currency="USD"),
        )
        bucket_sum = sum(k.cost_by_bucket.values(), Decimal(0))
        assert abs(bucket_sum - Decimal("0.30")) < Decimal("0.000001")
        tool_sum = sum(k.cost_by_tool.values(), Decimal(0))
        assert abs(tool_sum - Decimal("0.30")) < Decimal("0.000001")

    def test_cache_hit_rate_zero_when_no_tokens(self) -> None:
        k = compute_session_kpis([_e("Read", {"file_path": "/a"})], session_id="s", project="p")
        assert k.cache_hit_rate == 0.0

    def test_read_edit_ratio(self) -> None:
        entries = [
            _e("Read", {"file_path": "/a"}),
            _e("Read", {"file_path": "/a"}),
            _e("Edit", {"file_path": "/a"}),
        ]
        k = compute_session_kpis(entries, session_id="s", project="p")
        assert k.read_edit_ratio == 2.0

    def test_logs_kpis_event(self) -> None:
        buf = io.StringIO()
        configure_logging(level="DEBUG", json=True, stream=buf)
        log = get_logger("kpi-test")
        k = compute_session_kpis([_e("Read", {"file_path": "/a"})], session_id="abc", project="p")
        log_event(
            log,
            "codeburn.kpis.computed",
            session_id=k.session_id,
            one_shot_rate=k.one_shot_rate,
        )
        line = buf.getvalue().strip().splitlines()[-1]
        data = json.loads(line)
        assert data["event"] == "codeburn.kpis.computed"
        assert data["session_id"] == "abc"


