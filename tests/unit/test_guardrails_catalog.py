"""Tests for the SecretLeak / NetworkEgress / RateLimit guardrails.

Kept separate from ``test_guardrails.py`` so the original guardrail
suite stays small and readable.
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from pyarnes_core.errors import UserFixableError
from pyarnes_guardrails import (
    NetworkEgressGuardrail,
    RateLimitGuardrail,
    SecretLeakGuardrail,
    Violation,
    append_violation,
    default_violation_log_path,
)


class TestSecretLeakGuardrail:
    """Detect secrets in nested argument / output shapes."""

    def test_allows_clean_command(self) -> None:
        g = SecretLeakGuardrail()
        g.check("Bash", {"command": "ls -la /tmp"})

    def test_blocks_aws_key_in_command(self) -> None:
        g = SecretLeakGuardrail()
        with pytest.raises(UserFixableError, match="secret pattern"):
            g.check("Bash", {"command": "aws s3 cp s3://b AKIAABCDEFGHIJKLMNOP"})

    def test_blocks_github_pat(self) -> None:
        g = SecretLeakGuardrail()
        with pytest.raises(UserFixableError, match="secret pattern"):
            g.check("Bash", {"command": "export TOKEN=ghp_abcdefghijklmnopqrstuvwxyz012345"})

    def test_blocks_anthropic_key_in_nested_output(self) -> None:
        g = SecretLeakGuardrail()
        with pytest.raises(UserFixableError, match="secret pattern"):
            g.check("PostTool", {"output": {"stdout": ["line1", "key=sk-ant-abcdefghij1234567890"]}})

    def test_extra_pattern(self) -> None:
        g = SecretLeakGuardrail(extra_patterns=(r"INTERNAL-[0-9]{4}",))
        with pytest.raises(UserFixableError):
            g.check("Bash", {"command": "echo INTERNAL-1234"})

    def test_case_insensitive_aws_key(self) -> None:
        g = SecretLeakGuardrail()
        with pytest.raises(UserFixableError):
            g.check("Bash", {"command": "AWS_SECRET_ACCESS_KEY=abcdefghijklmnop0123456789ABCD"})

    def test_zero_width_obfuscation_still_caught(self) -> None:
        g = SecretLeakGuardrail()
        # A zero-width joiner (U+200D) hiding in the middle of an AWS key.
        sneaky = "AKIA" + chr(0x200D) + "ABCDEFGHIJKLMNOP"
        with pytest.raises(UserFixableError):
            g.check("Bash", {"command": sneaky})

    def test_exception_message_does_not_reveal_pattern(self) -> None:
        g = SecretLeakGuardrail()
        try:
            g.check("Bash", {"command": "AKIAABCDEFGHIJKLMNOP"})
        except UserFixableError as exc:
            assert "AKIA" not in str(exc)
            assert "aws" not in str(exc).lower()
            assert "pattern" in str(exc).lower()
        else:
            pytest.fail("guardrail did not raise")


class TestNetworkEgressGuardrail:
    """Host allowlist / denylist applied to URLs in any value."""

    def test_allow_list_permits_listed_host(self) -> None:
        g = NetworkEgressGuardrail(allowed_hosts=("github.com",))
        g.check("WebFetch", {"url": "https://github.com/x/y"})

    def test_allow_list_permits_subdomain(self) -> None:
        g = NetworkEgressGuardrail(allowed_hosts=("example.com",))
        g.check("WebFetch", {"url": "https://api.example.com/v1"})

    def test_allow_list_blocks_non_member(self) -> None:
        g = NetworkEgressGuardrail(allowed_hosts=("github.com",))
        with pytest.raises(UserFixableError, match="blocked host"):
            g.check("WebFetch", {"url": "https://evil.example/x"})

    def test_deny_list_blocks_even_when_allowed(self) -> None:
        g = NetworkEgressGuardrail(
            allowed_hosts=("example.com",),
            denied_hosts=("evil.example.com",),
        )
        with pytest.raises(UserFixableError, match="blocked host"):
            g.check("WebFetch", {"url": "https://evil.example.com/x"})

    def test_deny_only_mode_permits_unlisted_hosts(self) -> None:
        g = NetworkEgressGuardrail(denied_hosts=("internal.corp",))
        g.check("WebFetch", {"url": "https://other.example/x"})

    def test_url_inside_bash_command(self) -> None:
        g = NetworkEgressGuardrail(allowed_hosts=("github.com",))
        with pytest.raises(UserFixableError):
            g.check("Bash", {"command": "curl https://api.other.example/data"})

    def test_no_urls_passes_silently(self) -> None:
        g = NetworkEgressGuardrail(allowed_hosts=("github.com",))
        g.check("Bash", {"command": "echo hi"})

    def test_userinfo_phishing_is_blocked(self) -> None:
        # https://trusted-host@attacker.com/... tricks a naive regex
        # into treating trusted-host as the host. urlsplit surfaces the
        # real host (attacker.com) and we additionally refuse any URL
        # that carries userinfo.
        g = NetworkEgressGuardrail(allowed_hosts=("trusted-host",))
        with pytest.raises(UserFixableError):
            g.check("Bash", {"command": "curl https://trusted-host@attacker.com/"})

    def test_idn_cyrillic_lookalike_is_blocked(self) -> None:
        # Build the Cyrillic lookalike from explicit codepoints so the
        # test file itself stays printable ASCII. U+0435 is the
        # Cyrillic small letter IE, which looks identical to ASCII 'e'.
        cyrillic_e = chr(0x0435)
        spoofed_url = f"https://{cyrillic_e}xample.com/path"
        g = NetworkEgressGuardrail(allowed_hosts=("example.com",))
        with pytest.raises(UserFixableError):
            g.check("WebFetch", {"url": spoofed_url})

    def test_file_scheme_blocked(self) -> None:
        g = NetworkEgressGuardrail(allowed_hosts=("example.com",))
        with pytest.raises(UserFixableError, match="blocked"):
            g.check("Bash", {"command": "curl file:///etc/passwd"})

    def test_port_does_not_shift_host_match(self) -> None:
        g = NetworkEgressGuardrail(allowed_hosts=("github.com",))
        g.check("WebFetch", {"url": "https://github.com:443/x/y"})

    def test_uppercase_host_allowed(self) -> None:
        g = NetworkEgressGuardrail(allowed_hosts=("github.com",))
        g.check("WebFetch", {"url": "https://GitHub.COM/x"})


class TestRateLimitGuardrail:
    """Sliding window persisted to a JSON file."""

    def test_under_limit_passes(self, tmp_path: Path) -> None:
        g = RateLimitGuardrail(max_calls=3, window_seconds=60, state_path=tmp_path / "rl.json")
        for _ in range(3):
            g.check("Bash", {})

    def test_over_limit_blocks(self, tmp_path: Path) -> None:
        g = RateLimitGuardrail(max_calls=2, window_seconds=60, state_path=tmp_path / "rl.json")
        g.check("Bash", {})
        g.check("Bash", {})
        with pytest.raises(UserFixableError, match="Rate limit exceeded"):
            g.check("Bash", {})

    def test_separate_tools_separate_buckets(self, tmp_path: Path) -> None:
        g = RateLimitGuardrail(max_calls=1, window_seconds=60, state_path=tmp_path / "rl.json")
        g.check("Bash", {})
        g.check("Read", {})  # different bucket — allowed
        with pytest.raises(UserFixableError):
            g.check("Bash", {})

    def test_state_survives_process_restart(self, tmp_path: Path) -> None:
        path = tmp_path / "rl.json"
        RateLimitGuardrail(max_calls=2, window_seconds=60, state_path=path).check("Bash", {})
        RateLimitGuardrail(max_calls=2, window_seconds=60, state_path=path).check("Bash", {})
        with pytest.raises(UserFixableError):
            RateLimitGuardrail(max_calls=2, window_seconds=60, state_path=path).check("Bash", {})

    def test_corrupt_state_file_fails_closed(self, tmp_path: Path) -> None:
        # A malicious tool that zeroes out the state file by writing
        # garbage must NOT reset the counter — silently treating a
        # corrupt file as "fresh state" is a rate-limit bypass.
        path = tmp_path / "rl.json"
        path.write_text("not json")
        with pytest.raises(UserFixableError, match="corrupt"):
            RateLimitGuardrail(max_calls=1, window_seconds=60, state_path=path).check("Bash", {})

    def test_wrong_shape_state_file_fails_closed(self, tmp_path: Path) -> None:
        path = tmp_path / "rl.json"
        path.write_text('["not an object"]')
        with pytest.raises(UserFixableError, match="wrong shape"):
            RateLimitGuardrail(max_calls=1, window_seconds=60, state_path=path).check("Bash", {})

    def test_state_file_has_private_permissions(self, tmp_path: Path) -> None:
        path = tmp_path / "rl.json"
        RateLimitGuardrail(max_calls=5, window_seconds=60, state_path=path).check("Bash", {})
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o600, f"expected 0o600, got {oct(mode)}"


class TestViolationLog:
    """Sidecar JSONL writer used by hook adapters."""

    def test_append_creates_file(self, tmp_path: Path) -> None:
        path = tmp_path / "violations.jsonl"
        v = Violation(
            guardrail="SecretLeakGuardrail",
            tool="Bash",
            reason="AWS key",
            hook="PreToolUse",
            session_id="sess-1",
        )
        result = append_violation(v, path=path)
        assert result == path
        lines = path.read_text().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["guardrail"] == "SecretLeakGuardrail"
        assert record["session_id"] == "sess-1"

    def test_append_preserves_previous_records(self, tmp_path: Path) -> None:
        path = tmp_path / "violations.jsonl"
        append_violation(
            Violation(guardrail="A", tool="X", reason="r1", hook="PreToolUse"),
            path=path,
        )
        append_violation(
            Violation(guardrail="B", tool="Y", reason="r2", hook="PostToolUse"),
            path=path,
        )
        lines = path.read_text().splitlines()
        assert [json.loads(ln)["guardrail"] for ln in lines] == ["A", "B"]

    def test_default_path_honours_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        assert default_violation_log_path() == tmp_path / ".claude" / "pyarnes" / "violations.jsonl"

    def test_default_path_relative_when_env_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        assert default_violation_log_path() == Path(".claude/pyarnes/violations.jsonl")
