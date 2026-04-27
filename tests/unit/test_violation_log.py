"""Adversarial tests for violation_log.

The basic append / env-var tests live in test_guardrails_catalog.py.
This file adds:
- JSONL schema validation (required keys, timestamp sanity)
- 0o600 permission enforcement on the written file
- Concurrent append correctness under thread-level concurrency
"""

from __future__ import annotations

import asyncio
import json
import stat
from pathlib import Path

import pytest

from pyarnes_guardrails import Violation, append_violation


def _make_violation(**overrides: object) -> Violation:
    defaults: dict[str, object] = {
        "guardrail": "TestGuardrail",
        "tool": "Bash",
        "reason": "test reason",
        "hook": "PreToolUse",
    }
    defaults.update(overrides)
    return Violation(**defaults)  # type: ignore[arg-type]


class TestViolationLogSchema:
    """Every JSONL record must satisfy the documented schema."""

    def test_required_keys_present(self, tmp_path: Path) -> None:
        path = tmp_path / "v.jsonl"
        append_violation(_make_violation(), path=path)
        record = json.loads(path.read_text())
        for key in ("guardrail", "tool", "reason", "hook", "timestamp"):
            assert key in record, f"missing key: {key}"

    def test_timestamp_is_positive_float(self, tmp_path: Path) -> None:
        path = tmp_path / "v.jsonl"
        append_violation(_make_violation(), path=path)
        record = json.loads(path.read_text())
        ts = record["timestamp"]
        assert isinstance(ts, float), f"timestamp is {type(ts)}, expected float"
        assert ts > 0, "timestamp must be positive epoch seconds"

    def test_session_id_none_serializes_as_null(self, tmp_path: Path) -> None:
        path = tmp_path / "v.jsonl"
        append_violation(_make_violation(session_id=None), path=path)
        record = json.loads(path.read_text())
        assert record["session_id"] is None

    def test_session_id_value_preserved(self, tmp_path: Path) -> None:
        path = tmp_path / "v.jsonl"
        append_violation(_make_violation(session_id="sess-abc-123"), path=path)
        record = json.loads(path.read_text())
        assert record["session_id"] == "sess-abc-123"

    def test_reason_does_not_require_secret_text(self, tmp_path: Path) -> None:
        # Callers are responsible for keeping secrets out of reason.
        # The log must store whatever reason was supplied — this test
        # ensures the field is written faithfully, not silently dropped.
        path = tmp_path / "v.jsonl"
        reason = "secret pattern detected in arguments"
        append_violation(_make_violation(reason=reason), path=path)
        record = json.loads(path.read_text())
        assert record["reason"] == reason


class TestViolationLogPermissions:
    """The violations JSONL must be created private (0o600)."""

    def test_first_append_creates_file_0o600(self, tmp_path: Path) -> None:
        path = tmp_path / "violations.jsonl"
        append_violation(_make_violation(), path=path)
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o600, f"expected 0o600, got {oct(mode)}"

    def test_permission_preserved_after_multiple_appends(self, tmp_path: Path) -> None:
        path = tmp_path / "violations.jsonl"
        for i in range(5):
            append_violation(_make_violation(guardrail=f"G{i}"), path=path)
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o600, f"expected 0o600, got {oct(mode)}"


class TestViolationLogConcurrent:
    """Concurrent appends must produce exactly N complete JSONL records."""

    @pytest.mark.asyncio
    async def test_concurrent_thread_appends_all_records_present(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "violations.jsonl"
        n = 20

        async def append_one(i: int) -> None:
            v = _make_violation(guardrail=f"G{i}")
            await asyncio.to_thread(append_violation, v, path=path)

        await asyncio.gather(*[append_one(i) for i in range(n)])

        lines = path.read_text().splitlines()
        assert len(lines) == n, f"expected {n} lines, got {len(lines)}"
        # Every record must be valid JSON.
        records = [json.loads(ln) for ln in lines]
        guardrails = {r["guardrail"] for r in records}
        assert guardrails == {f"G{i}" for i in range(n)}
