"""Tests for lifecycle management."""

from __future__ import annotations

import pytest

from pyarnes.harness.lifecycle import Lifecycle, Phase


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
