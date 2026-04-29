"""Tests for ``pyarnes_core.observability.tokens.estimate_tokens``.

The estimator is the canonical token-count approximation used by compaction,
the burn optimizer, and the audit subpackage; behaviour is exercised here so
all three callers stay aligned.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pyarnes_core.observability import estimate_tokens


def test_empty_dict_is_two_chars() -> None:
    # `{}` → 2 chars → 0 tokens with the //4 rule.
    assert estimate_tokens({}) == 0


def test_simple_string_payload() -> None:
    # `"abcd"` → 6 chars → 1 token.
    assert estimate_tokens("abcd") == 1


def test_grows_with_payload_size() -> None:
    small = estimate_tokens({"x": "a" * 10})
    big = estimate_tokens({"x": "a" * 1000})
    assert big > small * 50


def test_handles_non_json_native_types_via_default_str() -> None:
    # ``datetime`` and ``Path`` are not JSON-native; the estimator must not
    # raise — it falls back to ``str`` via ``json.dumps(default=str)``.
    payload = {"when": datetime(2026, 1, 1, tzinfo=UTC), "where": Path("/tmp/x")}  # noqa: S108 — placeholder, never written
    assert estimate_tokens(payload) > 0


def test_list_of_messages() -> None:
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    # Smoke test: messages have non-zero size and the estimator reflects it.
    assert estimate_tokens(messages) > 0
