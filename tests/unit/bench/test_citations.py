"""Tests for :mod:`pyarnes_bench._citations`."""

from __future__ import annotations

import pytest

from pyarnes_bench._citations import URL_RE, strip_markers


class TestStripMarkers:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("The sky is blue [1].", "The sky is blue ."),
            ("Multiple sources [1, 2, 3] agree.", "Multiple sources  agree."),
            ("Dash range [1-3] works.", "Dash range  works."),
            ("See [Smith 2023] and [Jones 2024].", "See  and ."),
            ("No markers at all.", "No markers at all."),
        ],
    )
    def test_patterns(self, raw: str, expected: str) -> None:
        assert strip_markers(raw) == expected

    def test_idempotent(self) -> None:
        once = strip_markers("Claim [1] foo [2,3] bar.")
        twice = strip_markers(once)
        assert once == twice

    def test_multiline(self) -> None:
        text = "Para one [1].\n\nPara two [Smith 2023].\n"
        assert strip_markers(text) == "Para one .\n\nPara two .\n"

    def test_does_not_eat_brackets_with_newlines(self) -> None:
        # Brackets spanning newlines are NOT markers — they're likely code.
        text = "code block [\n  x = 1\n]"
        assert strip_markers(text) == text


class TestUrlRegex:
    @pytest.mark.parametrize(
        "text",
        [
            "See https://example.com/path for details.",
            "Mixed http://a.org and https://b.org.",
            "Trailing punctuation https://example.com/foo.",
        ],
    )
    def test_finds_urls(self, text: str) -> None:
        assert URL_RE.search(text) is not None

    def test_captures_full_path(self) -> None:
        match = URL_RE.search("See https://example.com/a/b?x=1 done.")
        assert match is not None
        assert match.group(0) == "https://example.com/a/b?x=1"

    def test_excludes_trailing_paren(self) -> None:
        match = URL_RE.search("(see https://example.com/foo)")
        assert match is not None
        assert match.group(0) == "https://example.com/foo"
