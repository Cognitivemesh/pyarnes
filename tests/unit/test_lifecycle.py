"""Tests for lifecycle management."""

from __future__ import annotations

import io
import json

import pytest

from pyarnes_core.lifecycle import Lifecycle, Phase
from pyarnes_core.observe.logger import LogFormat, configure_logging


class TestLifecycle:
    """Lifecycle FSM transitions."""

    def test_initial_phase(self) -> None:
        lc = Lifecycle()
        assert lc.phase == Phase.INIT

    def test_start(self) -> None:
        lc = Lifecycle()
        lc.start()
        assert lc.phase == Phase.RUNNING

    def test_pause_resume(self) -> None:
        lc = Lifecycle()
        lc.start()
        lc.pause()
        assert lc.phase == Phase.PAUSED
        lc.resume()
        assert lc.phase == Phase.RUNNING

    def test_complete(self) -> None:
        lc = Lifecycle()
        lc.start()
        lc.complete()
        assert lc.phase == Phase.COMPLETED
        assert lc.is_terminal is True

    def test_fail_from_running(self) -> None:
        lc = Lifecycle()
        lc.start()
        lc.fail()
        assert lc.phase == Phase.FAILED
        assert lc.is_terminal is True

    def test_fail_from_init(self) -> None:
        lc = Lifecycle()
        lc.fail()
        assert lc.phase == Phase.FAILED

    def test_invalid_transition(self) -> None:
        lc = Lifecycle()
        lc.start()
        lc.complete()
        with pytest.raises(ValueError, match="Invalid transition"):
            lc.start()

    def test_history_tracking(self) -> None:
        lc = Lifecycle()
        lc.start()
        lc.pause()
        lc.resume()
        lc.complete()
        assert len(lc.history) == 4
        assert lc.history[0]["from"] == "init"
        assert lc.history[0]["to"] == "running"

    def test_metadata(self) -> None:
        lc = Lifecycle(metadata={"session_id": "abc123"})
        assert lc.metadata["session_id"] == "abc123"


class TestLifecycleStructuredEvents:
    """Transition events must land in record.extra as JSON fields."""

    def test_transition_emits_structured_fields(self) -> None:
        sink = io.StringIO()
        configure_logging(level="INFO", fmt=LogFormat.JSON, stream=sink)
        try:
            lc = Lifecycle()
            lc.start()
        finally:
            configure_logging(level="INFO", fmt=LogFormat.JSON)

        lines = [ln for ln in sink.getvalue().splitlines() if ln.strip()]
        transition_records = [json.loads(ln) for ln in lines if json.loads(ln).get("event") == "lifecycle.transition"]
        assert transition_records, "lifecycle.transition event not emitted"
        record = transition_records[0]
        assert record["from_phase"] == "init"
        assert record["to_phase"] == "running"
