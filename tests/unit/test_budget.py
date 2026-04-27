"""Tests for Budget and Lifecycle persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyarnes_core import Budget, Lifecycle, Phase
from pyarnes_core.errors import UserFixableError


class TestBudgetConsume:
    """Budget.consume returns a new immutable record."""

    def test_initial_totals_zero(self) -> None:
        b = Budget()
        assert b.calls == 0
        assert b.seconds == 0.0
        assert b.tokens == 0

    def test_consume_is_immutable(self) -> None:
        b = Budget()
        b2 = b.consume(calls=1, seconds=0.5, tokens=100)
        assert b.calls == 0 and b.seconds == 0.0 and b.tokens == 0
        assert b2.calls == 1
        assert b2.seconds == 0.5
        assert b2.tokens == 100

    def test_consume_accumulates(self) -> None:
        b = Budget().consume(calls=1).consume(calls=2, tokens=50)
        assert b.calls == 3
        assert b.tokens == 50


class TestBudgetExhaustion:
    """is_exhausted / exceeded_cap / raise_if_exhausted."""

    def test_no_caps_never_exhausted(self) -> None:
        assert Budget(calls=1_000_000).is_exhausted() is False

    def test_call_cap(self) -> None:
        b = Budget(max_calls=2).consume(calls=2)
        assert b.exceeded_cap() == "calls"
        assert b.is_exhausted() is True

    def test_time_cap(self) -> None:
        b = Budget(max_seconds=1.0).consume(seconds=1.5)
        assert b.exceeded_cap() == "seconds"

    def test_token_cap(self) -> None:
        b = Budget(max_tokens=100).consume(tokens=100)
        assert b.exceeded_cap() == "tokens"

    def test_first_cap_wins(self) -> None:
        # Calls are checked before seconds; both are exhausted.
        b = Budget(max_calls=1, max_seconds=1.0).consume(calls=1, seconds=2.0)
        assert b.exceeded_cap() == "calls"

    def test_raise_if_exhausted(self) -> None:
        b = Budget(max_calls=1).consume(calls=1)
        with pytest.raises(UserFixableError, match="Budget cap"):
            b.raise_if_exhausted()

    def test_raise_if_not_exhausted_is_silent(self) -> None:
        Budget(max_calls=10).raise_if_exhausted()  # no-op


class TestBudgetRoundtrip:
    """JSON round-trip via as_dict / from_dict."""

    def test_roundtrip(self) -> None:
        b = Budget(max_calls=10, max_seconds=60.0, max_tokens=1000, calls=3, seconds=12.5, tokens=220)
        recovered = Budget.from_dict(b.as_dict())
        assert recovered == b


class TestLifecyclePersistence:
    """Lifecycle.dump / load round-trips phase + metadata + budget."""

    def test_dump_load_preserves_phase(self, tmp_path: Path) -> None:
        lc = Lifecycle()
        lc.start()
        lc.pause()
        path = lc.dump(tmp_path / "lc.json")
        restored = Lifecycle.load(path)
        assert restored.phase == Phase.PAUSED

    def test_dump_load_preserves_metadata(self, tmp_path: Path) -> None:
        lc = Lifecycle(metadata={"session_id": "abc123", "user": "u1"})
        restored = Lifecycle.load(lc.dump(tmp_path / "lc.json"))
        assert restored.metadata == {"session_id": "abc123", "user": "u1"}

    def test_dump_load_preserves_budget(self, tmp_path: Path) -> None:
        lc = Lifecycle(budget=Budget(max_calls=10, calls=3))
        restored = Lifecycle.load(lc.dump(tmp_path / "lc.json"))
        assert restored.budget is not None
        assert restored.budget.calls == 3
        assert restored.budget.max_calls == 10

    def test_dump_without_budget_roundtrips_as_none(self, tmp_path: Path) -> None:
        lc = Lifecycle()
        restored = Lifecycle.load(lc.dump(tmp_path / "lc.json"))
        assert restored.budget is None

    def test_dump_creates_parent_directories(self, tmp_path: Path) -> None:
        lc = Lifecycle()
        path = tmp_path / "nested" / "deep" / "lc.json"
        lc.dump(path)
        assert path.is_file()

    def test_history_is_not_persisted(self, tmp_path: Path) -> None:
        lc = Lifecycle()
        lc.start()
        lc.complete()
        restored = Lifecycle.load(lc.dump(tmp_path / "lc.json"))
        assert restored.history == []
