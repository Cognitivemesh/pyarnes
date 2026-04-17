"""Tests for guardrails."""

from __future__ import annotations

import pytest

from pyarnes.harness.errors import UserFixableError
from pyarnes.harness.guardrails import (
    CommandGuardrail,
    GuardrailChain,
    PathGuardrail,
    ToolAllowlistGuardrail,
)


class TestPathGuardrail:
    """PathGuardrail blocks paths outside allowed roots."""

    def test_allowed_path(self) -> None:
        g = PathGuardrail(allowed_roots=("/workspace",))
        g.check("read_file", {"path": "/workspace/src/main.py"})

    def test_blocked_path(self) -> None:
        g = PathGuardrail(allowed_roots=("/workspace",))
        with pytest.raises(UserFixableError, match="outside allowed roots"):
            g.check("read_file", {"path": "/etc/passwd"})

    def test_no_path_arg_passes(self) -> None:
        g = PathGuardrail()
        g.check("some_tool", {"text": "hello"})


class TestCommandGuardrail:
    """CommandGuardrail blocks dangerous shell patterns."""

    def test_safe_command(self) -> None:
        g = CommandGuardrail()
        g.check("shell", {"command": "ls -la"})

    def test_rm_rf_slash(self) -> None:
        g = CommandGuardrail()
        with pytest.raises(UserFixableError, match="blocked"):
            g.check("shell", {"command": "rm -rf /"})

    def test_sudo(self) -> None:
        g = CommandGuardrail()
        with pytest.raises(UserFixableError, match="blocked"):
            g.check("shell", {"command": "sudo apt install foo"})

    def test_non_string_command(self) -> None:
        g = CommandGuardrail()
        g.check("shell", {"command": 42})  # type: ignore[dict-item]


class TestToolAllowlistGuardrail:
    """ToolAllowlistGuardrail restricts which tools can be called."""

    def test_allowed(self) -> None:
        g = ToolAllowlistGuardrail(allowed_tools=frozenset({"echo", "read"}))
        g.check("echo", {})

    def test_blocked(self) -> None:
        g = ToolAllowlistGuardrail(allowed_tools=frozenset({"echo"}))
        with pytest.raises(UserFixableError, match="not in the allowlist"):
            g.check("delete_all", {})

    def test_empty_allowlist_permits_all(self) -> None:
        g = ToolAllowlistGuardrail()
        g.check("anything", {})


class TestGuardrailChain:
    """GuardrailChain composes multiple guardrails."""

    def test_all_pass(self) -> None:
        chain = GuardrailChain(
            guardrails=[
                PathGuardrail(allowed_roots=("/workspace",)),
                CommandGuardrail(),
            ]
        )
        chain.check("shell", {"command": "echo hi", "path": "/workspace/file.txt"})

    def test_first_failure_stops(self) -> None:
        chain = GuardrailChain(
            guardrails=[
                PathGuardrail(allowed_roots=("/workspace",)),
                CommandGuardrail(),
            ]
        )
        with pytest.raises(UserFixableError):
            chain.check("shell", {"path": "/root/.ssh/id_rsa"})
