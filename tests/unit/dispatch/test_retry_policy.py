"""Tests for dispatch.atoms.retry_policy — B5, B6 prep."""

from __future__ import annotations

from pyarnes_core.dispatch.atoms import merge_retry_caps, next_delay


class TestMergeRetryCaps:
    """merge_retry_caps takes max of config and error overrides."""

    def test_no_error_overrides(self) -> None:
        policy = merge_retry_caps(config_max=2, config_delay=1.0)
        assert policy.max_retries == 2
        assert policy.base_delay_seconds == 1.0

    def test_error_raises_max(self) -> None:
        # B5: a TransientError asking for 5 retries should override default 2.
        policy = merge_retry_caps(config_max=2, config_delay=1.0, error_max=5)
        assert policy.max_retries == 5

    def test_error_does_not_lower_max(self) -> None:
        # If loop is configured stricter than the error hint, keep the loop value.
        policy = merge_retry_caps(config_max=10, config_delay=1.0, error_max=2)
        assert policy.max_retries == 10

    def test_error_raises_delay(self) -> None:
        # B6: a TransientError asking for a longer delay should take effect.
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
        policy = merge_retry_caps(config_max=2, config_delay=0.5, error_delay=2.0)
        # Base becomes 2.0; second retry is 4.0.
        assert next_delay(policy, attempt=1) == 4.0
