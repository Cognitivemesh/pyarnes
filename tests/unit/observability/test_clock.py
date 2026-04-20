"""Tests for observability.atoms.clock — B7 prep."""

from __future__ import annotations

import time

from pyarnes_core.observability.atoms import iso_now, monotonic_duration, start_timer


class TestIsoNow:
    """iso_now returns an ISO-8601 UTC timestamp."""

    def test_has_timezone_marker(self) -> None:
        now = iso_now()
        # UTC isoformat ends with +00:00 or Z-like marker.
        assert "+00:00" in now or now.endswith("Z")

    def test_is_sortable(self) -> None:
        a = iso_now()
        time.sleep(0.001)
        b = iso_now()
        assert b >= a


class TestStartTimer:
    """start_timer captures iso and monotonic together."""

    def test_returns_two_values(self) -> None:
        started_at, start_mono = start_timer()
        assert isinstance(started_at, str)
        assert isinstance(start_mono, float)


class TestMonotonicDuration:
    """monotonic_duration measures wall-clock elapsed time."""

    def test_measures_elapsed(self) -> None:
        _, start_mono = start_timer()
        time.sleep(0.01)
        finished_at, duration = monotonic_duration(start_mono)
        assert isinstance(finished_at, str)
        assert duration >= 0.01

    def test_hoisted_outside_loop(self) -> None:
        # B7 shape: call start_timer ONCE, then call monotonic_duration
        # after multiple sub-operations. Duration reflects the full span.
        _, start_mono = start_timer()
        for _ in range(3):
            time.sleep(0.005)
        _, duration = monotonic_duration(start_mono)
        assert duration >= 0.015
