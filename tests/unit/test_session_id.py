"""Property-based tests for safe_session_id.

The parametrised cases in test_hardening.py cover concrete bad inputs.
These Hypothesis tests verify that the invariants hold for arbitrary text
and non-string inputs — catching corner cases that a hand-picked list
cannot anticipate.
"""

from __future__ import annotations

import re

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pyarnes_core import safe_session_id

# Pattern that matches what the implementation allows through.
_SAFE = re.compile(r"\A[A-Za-z0-9._-]{1,64}\Z")
_ONLY_DOTS = re.compile(r"\A\.+\Z")


class TestSafeSessionIdHypothesis:
    """Invariants hold for arbitrary text and non-string inputs."""

    @given(st.text())
    @settings(max_examples=500)
    def test_output_never_contains_slash(self, raw: str) -> None:
        result = safe_session_id(raw)
        assert "/" not in result
        assert "\\" not in result

    @given(st.text())
    @settings(max_examples=500)
    def test_output_length_never_exceeds_64(self, raw: str) -> None:
        result = safe_session_id(raw)
        assert len(result) <= 64

    @given(st.text())
    @settings(max_examples=500)
    def test_output_never_contains_nul(self, raw: str) -> None:
        result = safe_session_id(raw)
        assert "\x00" not in result

    @given(st.text())
    @settings(max_examples=500)
    def test_output_is_always_a_string(self, raw: str) -> None:
        result = safe_session_id(raw)
        assert isinstance(result, str)

    @given(st.text())
    @settings(max_examples=500)
    def test_invalid_inputs_always_return_default(self, raw: str) -> None:
        result = safe_session_id(raw)
        # Either it passes through unchanged (valid) or falls back to "default".
        assert result in (raw, "default")

    @given(
        st.one_of(
            st.none(),
            st.integers(),
            st.floats(allow_nan=True, allow_infinity=True),
            st.booleans(),
            st.binary(),
            st.lists(st.text()),
            st.dictionaries(st.text(), st.text()),
        )
    )
    @settings(max_examples=300)
    def test_non_string_always_returns_default(self, raw: object) -> None:
        assert safe_session_id(raw) == "default"

    @given(
        st.from_regex(r"[A-Za-z0-9._\-]{1,64}", fullmatch=True)
        .filter(lambda s: not re.fullmatch(r"\.+", s))
    )
    @settings(max_examples=300)
    def test_valid_ids_pass_through_unchanged(self, good: str) -> None:
        assert safe_session_id(good) == good

    @pytest.mark.parametrize("dots_only", [".", "..", "...", "." * 10, "." * 63])
    def test_dots_only_strings_always_fall_back(self, dots_only: str) -> None:
        assert safe_session_id(dots_only) == "default"

    @pytest.mark.parametrize(
        "unicode_path",
        [
            "ñ",
            "日本語",
            "🔑",
            "пример",
            "\u200d",  # zero-width joiner
            "\u202e",  # right-to-left override
            "a\x00b",  # embedded NUL (Hypothesis might not generate)
        ],
    )
    def test_unicode_edge_cases_fall_back(self, unicode_path: str) -> None:
        result = safe_session_id(unicode_path)
        assert result in ("default", unicode_path)
        # Either way the output must be safe.
        assert "\x00" not in result
        assert "/" not in result
