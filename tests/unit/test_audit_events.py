"""Tests for the typed audit event emitters."""

from __future__ import annotations

import io
import json

from pyarnes_bench.audit.events import (
    log_audit_analyzed,
    log_audit_finding,
    log_audit_indexed,
)
from pyarnes_core.observe.logger import LogFormat, configure_logging, get_logger


def _record(sink: io.StringIO) -> dict:
    line = sink.getvalue().strip().splitlines()[-1]
    return json.loads(line)


def test_log_audit_indexed_emits_required_fields() -> None:
    sink = io.StringIO()
    configure_logging(level="INFO", fmt=LogFormat.JSON, stream=sink)
    logger = get_logger("audit-events-test")
    log_audit_indexed(
        logger,
        "/repo",
        files=10,
        nodes=100,
        edges=200,
        duration_ms=12.5,
        session_id="sid",
        trace_id="tid",
        step=3,
    )
    record = _record(sink)
    assert record["event"] == "audit.indexed"
    assert record["root"] == "/repo"
    assert record["files"] == 10
    assert record["session_id"] == "sid"
    assert record["trace_id"] == "tid"
    assert record["step"] == 3


def test_log_audit_analyzed_records_kind_and_count() -> None:
    sink = io.StringIO()
    configure_logging(level="INFO", fmt=LogFormat.JSON, stream=sink)
    logger = get_logger("audit-events-test-2")
    log_audit_analyzed(
        logger,
        "god_nodes",
        count=7,
        session_id="sid",
        trace_id="tid",
        step=1,
    )
    record = _record(sink)
    assert record["event"] == "audit.analyzed"
    assert record["kind"] == "god_nodes"
    assert record["count"] == 7


def test_log_audit_finding_carries_detail() -> None:
    sink = io.StringIO()
    configure_logging(level="INFO", fmt=LogFormat.JSON, stream=sink)
    logger = get_logger("audit-events-test-3")
    log_audit_finding(
        logger,
        "circular_import",
        "pkg.a",
        "high",
        session_id="sid",
        trace_id="tid",
        step=2,
        detail={"cycle": ["pkg.a", "pkg.b"]},
    )
    record = _record(sink)
    assert record["event"] == "audit.finding"
    assert record["category"] == "circular_import"
    assert record["target"] == "pkg.a"
    assert record["severity"] == "high"
    assert record["detail"] == {"cycle": ["pkg.a", "pkg.b"]}
