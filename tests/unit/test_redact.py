"""Tests for pyarnes_core.safety.redact."""

from pyarnes_core.safety.redact import REDACTED, redact, redact_dict


def test_clean_string_unchanged():
    assert redact("hello world") == "hello world"


def test_aws_access_key():
    s = "key is AKIAIOSFODNN7EXAMPLE more text"
    assert REDACTED in redact(s)
    assert "AKIAIOSFODNN7EXAMPLE" not in redact(s)


def test_github_token():
    token = "ghp_" + "A" * 36
    result = redact(f"token={token}")
    assert token not in result
    assert REDACTED in result


def test_private_key_pem():
    pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIabcdef\n-----END RSA PRIVATE KEY-----"
    result = redact(pem)
    assert REDACTED in result
    assert "MIIabcdef" not in result


def test_redact_dict_string_value():
    token = "ghp_" + "B" * 36
    d = {"output": f"result token={token}"}
    result = redact_dict(d)
    assert token not in result["output"]
    assert REDACTED in result["output"]


def test_redact_dict_does_not_mutate():
    token = "ghp_" + "C" * 36
    original = {"k": f"v {token}"}
    redact_dict(original)
    assert token in original["k"]


def test_redact_dict_nested():
    token = "ghp_" + "D" * 36
    d = {"outer": {"inner": token}}
    result = redact_dict(d)
    assert token not in result["outer"]["inner"]


def test_redact_dict_list_values():
    token = "ghp_" + "E" * 36
    d = {"items": [token, "clean"]}
    result = redact_dict(d)
    assert token not in result["items"][0]
    assert result["items"][1] == "clean"


def test_empty_string():
    assert redact("") == ""
