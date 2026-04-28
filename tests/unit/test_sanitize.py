"""Tests for pyarnes_core.safety.sanitize."""

from pyarnes_core.safety.sanitize import sanitize_messages, sanitize_str


def test_clean_string_unchanged():
    assert sanitize_str("hello world\nline2\ttabbed") == "hello world\nline2\ttabbed"


def test_surrogate_removed():
    s = "before\ud800after"
    result = sanitize_str(s)
    assert "\ud800" not in result
    assert "before" in result
    assert "after" in result


def test_null_byte_removed():
    assert sanitize_str("a\x00b") == "ab"


def test_control_chars_removed():
    # BEL, BS, VT, FF are stripped; HT LF CR are kept
    assert sanitize_str("\x07\x08\x0b\x0c") == ""
    assert sanitize_str("\t\n\r") == "\t\n\r"


def test_del_removed():
    assert sanitize_str("a\x7fb") == "ab"


def test_c1_block_removed():
    assert sanitize_str("a\x80\x9fb") == "ab"


def test_sanitize_messages_nested():
    messages = [
        {"role": "user", "content": "hello\ud800world"},
        {"role": "tool", "content": [{"type": "text", "text": "data\x00here"}]},
    ]
    result = sanitize_messages(messages)
    assert result[0]["content"] == "helloworld"
    assert result[1]["content"][0]["text"] == "datahere"


def test_sanitize_messages_does_not_mutate():
    original = [{"role": "user", "content": "ok\x00bad"}]
    sanitize_messages(original)
    assert original[0]["content"] == "ok\x00bad"


def test_empty_string():
    assert sanitize_str("") == ""


def test_unicode_emoji_preserved():
    # Emoji are valid Unicode and must not be stripped
    assert sanitize_str("hello 🎉") == "hello 🎉"
