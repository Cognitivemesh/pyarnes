"""Tests for tool-call JSON argument repair."""

from __future__ import annotations

import pytest

from pyarnes_core.errors import LLMRecoverableError
from pyarnes_harness.repair import repair_json_args


def test_valid_json_fast_path() -> None:
    result = repair_json_args('{"key": "value", "n": 42}')
    assert result == {"key": "value", "n": 42}


def test_empty_object() -> None:
    assert repair_json_args("{}") == {}


def test_trailing_comma_in_object() -> None:
    result = repair_json_args('{"a": 1, "b": 2,}')
    assert result == {"a": 1, "b": 2}


def test_trailing_comma_in_array_value() -> None:
    result = repair_json_args('{"items": [1, 2, 3,]}')
    assert result == {"items": [1, 2, 3]}


def test_unclosed_brace() -> None:
    result = repair_json_args('{"a": 1, "b": 2')
    assert result == {"a": 1, "b": 2}


def test_unclosed_bracket_in_value() -> None:
    # Missing ] and } at the end — _close_open appends them
    result = repair_json_args('{"items": [1, 2, 3')
    assert result["items"] == [1, 2, 3]


def test_control_chars_stripped() -> None:
    # \x00 null byte and \x01 control char inside a value
    raw = '{"cmd": "hello\x00world\x01"}'
    result = repair_json_args(raw)
    assert result == {"cmd": "helloworld"}


def test_unrepairable_raises_llm_recoverable_error() -> None:
    with pytest.raises(LLMRecoverableError):
        repair_json_args("not json at all !!!{{{")


def test_empty_string_raises_llm_recoverable_error() -> None:
    with pytest.raises(LLMRecoverableError):
        repair_json_args("")


def test_nested_object_valid() -> None:
    raw = '{"outer": {"inner": true}}'
    assert repair_json_args(raw) == {"outer": {"inner": True}}
