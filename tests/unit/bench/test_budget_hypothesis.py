"""Property-based tests for Budget.

The specific-value tests live in tests/unit/test_budget.py.
These Hypothesis tests verify invariants that hold for arbitrary inputs.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pyarnes_core import Budget
from pyarnes_core.errors import UserFixableError

_calls = st.integers(min_value=0, max_value=1_000_000)
_tokens = st.integers(min_value=0, max_value=10_000_000)
_seconds = st.floats(min_value=0.0, max_value=86400.0, allow_nan=False, allow_infinity=False)
_cap_calls = st.one_of(st.none(), _calls)
_cap_tokens = st.one_of(st.none(), _tokens)
_cap_seconds = st.one_of(st.none(), _seconds)


class TestBudgetRoundtripHypothesis:
    """as_dict / from_dict must be exact inverses."""

    @given(calls=_calls, tokens=_tokens, seconds=_seconds)
    @settings(max_examples=500)
    def test_roundtrip_preserves_counters(self, calls: int, tokens: int, seconds: float) -> None:
        original = Budget(calls=calls, tokens=tokens, seconds=seconds)
        restored = Budget.from_dict(original.as_dict())
        assert restored.calls == calls
        assert restored.tokens == tokens
        assert restored.seconds == pytest.approx(seconds)

    @given(
        max_calls=_cap_calls,
        max_tokens=_cap_tokens,
        max_seconds=_cap_seconds,
    )
    @settings(max_examples=300)
    def test_roundtrip_preserves_caps(
        self,
        max_calls: int | None,
        max_tokens: int | None,
        max_seconds: float | None,
    ) -> None:
        b = Budget(max_calls=max_calls, max_tokens=max_tokens, max_seconds=max_seconds)
        restored = Budget.from_dict(b.as_dict())
        assert restored.max_calls == max_calls
        assert restored.max_tokens == max_tokens
        if max_seconds is None:
            assert restored.max_seconds is None
        else:
            assert restored.max_seconds == pytest.approx(max_seconds)


class TestBudgetCapEnforcementHypothesis:
    """Cap logic is consistent for arbitrary (counter, cap) pairs."""

    @given(calls=_calls, cap=st.integers(min_value=1, max_value=1_000_000))
    @settings(max_examples=500)
    def test_calls_cap_exhausted_exactly_at_boundary(self, calls: int, cap: int) -> None:
        b = Budget(max_calls=cap, calls=calls)
        if calls >= cap:
            assert b.is_exhausted()
            assert b.exceeded_cap() == "calls"
        else:
            # Only exhausted if calls cap is hit; other caps are None so they
            # don't count here.
            assert not b.is_exhausted()

    @given(tokens=_tokens, cap=st.integers(min_value=1, max_value=10_000_000))
    @settings(max_examples=500)
    def test_tokens_cap_exhausted_exactly_at_boundary(self, tokens: int, cap: int) -> None:
        b = Budget(max_tokens=cap, tokens=tokens)
        if tokens >= cap:
            assert b.is_exhausted()
        else:
            assert not b.is_exhausted()

    @given(calls=_calls, seconds=_seconds)
    @settings(max_examples=500)
    def test_calls_cap_checked_before_seconds_cap(self, calls: int, seconds: float) -> None:
        """exceeded_cap returns 'calls' when both calls and seconds caps are hit."""
        b = Budget(max_calls=calls, max_seconds=seconds, calls=calls, seconds=seconds)
        # Both caps are exhausted — calls is checked first.
        assert b.exceeded_cap() == "calls"

    @given(
        calls=st.integers(min_value=0, max_value=100),
        tokens=st.integers(min_value=0, max_value=100),
        seconds=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=300)
    def test_consume_returns_new_instance(self, calls: int, tokens: int, seconds: float) -> None:
        original = Budget()
        updated = original.consume(calls=calls, tokens=tokens, seconds=seconds)
        # consume is pure / returns a new object.
        assert updated is not original
        assert updated.calls == calls
        assert updated.tokens == tokens
        assert updated.seconds == pytest.approx(seconds)

    @given(
        calls=_calls,
        cap=st.integers(min_value=1, max_value=1_000_000),
    )
    @settings(max_examples=300)
    def test_raise_if_exhausted_only_raises_when_cap_hit(self, calls: int, cap: int) -> None:
        b = Budget(max_calls=cap, calls=calls)
        if calls >= cap:
            with pytest.raises(UserFixableError):
                b.raise_if_exhausted()
        else:
            b.raise_if_exhausted()  # must not raise


class TestBudgetConsumeArithmetic:
    """consume accumulates counters correctly for arbitrary increments."""

    @given(
        n=st.integers(min_value=1, max_value=100),
        per_call=st.integers(min_value=0, max_value=10),
        per_token=st.integers(min_value=0, max_value=1000),
        per_second=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=300)
    def test_sequential_consume_accumulates_correctly(
        self, n: int, per_call: int, per_token: int, per_second: float
    ) -> None:
        b = Budget()
        for _ in range(n):
            b = b.consume(calls=per_call, tokens=per_token, seconds=per_second)
        assert b.calls == n * per_call
        assert b.tokens == n * per_token
        assert b.seconds == pytest.approx(n * per_second)
