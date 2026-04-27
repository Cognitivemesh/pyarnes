"""Tests for dispatch.atoms.retry_policy."""

from __future__ import annotations

from itertools import pairwise

from hypothesis import given, settings
from hypothesis import strategies as st

from pyarnes_core.dispatch import merge_retry_caps, next_delay


class TestMergeRetryCaps:
    """merge_retry_caps takes max of config and error overrides."""

    def test_no_error_overrides(self) -> None:
        policy = merge_retry_caps(config_max=2, config_delay=1.0)
        assert policy.max_retries == 2
        assert policy.base_delay_seconds == 1.0

    def test_error_raises_max(self) -> None:
        """TransientError asking for 5 retries overrides config default of 2."""
        policy = merge_retry_caps(config_max=2, config_delay=1.0, error_max=5)
        assert policy.max_retries == 5

    def test_error_does_not_lower_max(self) -> None:
        """A stricter loop config keeps the loop's value."""
        policy = merge_retry_caps(config_max=10, config_delay=1.0, error_max=2)
        assert policy.max_retries == 10

    def test_error_raises_delay(self) -> None:
        """TransientError delay overrides a shorter config base."""
        policy = merge_retry_caps(config_max=2, config_delay=0.5, error_delay=2.0)
        assert policy.base_delay_seconds == 2.0

    def test_error_does_not_shorten_delay(self) -> None:
        policy = merge_retry_caps(config_max=2, config_delay=5.0, error_delay=1.0)
        assert policy.base_delay_seconds == 5.0


class TestNextDelay:
    """next_delay produces exponential backoff from the policy's base."""

    def test_first_retry(self) -> None:
        policy = merge_retry_caps(config_max=2, config_delay=1.0)
        assert next_delay(policy, attempt=0) == 1.0

    def test_second_retry_doubled(self) -> None:
        policy = merge_retry_caps(config_max=2, config_delay=1.0)
        assert next_delay(policy, attempt=1) == 2.0

    def test_backoff_uses_merged_base(self) -> None:
        """Merged base 2.0 means second retry is 4.0."""
        policy = merge_retry_caps(config_max=2, config_delay=0.5, error_delay=2.0)
        assert next_delay(policy, attempt=1) == 4.0


class TestNextDelayHypothesis:
    """Property invariants for next_delay under arbitrary but realistic inputs."""

    _base = st.floats(min_value=0.001, max_value=10.0, allow_nan=False, allow_infinity=False)
    _attempt = st.integers(min_value=0, max_value=20)

    @given(base=_base, attempt=_attempt)
    @settings(max_examples=500)
    def test_delay_always_non_negative(self, base: float, attempt: int) -> None:
        policy = merge_retry_caps(config_max=3, config_delay=base)
        delay = next_delay(policy, attempt)
        assert delay >= 0.0

    @given(base=_base)
    @settings(max_examples=300)
    def test_delay_monotonically_non_decreasing(self, base: float) -> None:
        policy = merge_retry_caps(config_max=5, config_delay=base)
        delays = [next_delay(policy, i) for i in range(5)]
        for prev, nxt in pairwise(delays):
            assert nxt >= prev, f"delay decreased: {prev} -> {nxt}"

    @given(
        config_max=st.integers(min_value=0, max_value=10),
        config_delay=_base,
        error_max=st.one_of(st.none(), st.integers(min_value=0, max_value=10)),
        error_delay=st.one_of(st.none(), _base),
    )
    @settings(max_examples=500)
    def test_merged_max_is_at_least_both_inputs(
        self,
        config_max: int,
        config_delay: float,
        error_max: int | None,
        error_delay: float | None,
    ) -> None:
        policy = merge_retry_caps(
            config_max=config_max,
            config_delay=config_delay,
            error_max=error_max,
            error_delay=error_delay,
        )
        assert policy.max_retries >= config_max
        if error_max is not None:
            assert policy.max_retries >= error_max

    @given(
        config_max=st.integers(min_value=0, max_value=10),
        config_delay=_base,
        error_max=st.one_of(st.none(), st.integers(min_value=0, max_value=10)),
        error_delay=st.one_of(st.none(), _base),
    )
    @settings(max_examples=500)
    def test_merged_delay_is_at_least_both_inputs(
        self,
        config_max: int,
        config_delay: float,
        error_max: int | None,
        error_delay: float | None,
    ) -> None:
        policy = merge_retry_caps(
            config_max=config_max,
            config_delay=config_delay,
            error_max=error_max,
            error_delay=error_delay,
        )
        assert policy.base_delay_seconds >= config_delay
        if error_delay is not None:
            assert policy.base_delay_seconds >= error_delay
