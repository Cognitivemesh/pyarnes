"""Safety guardrails for the agentic harness.

Guardrails wrap tool execution and enforce limits on what the system can
touch.  They are composable — stack multiple guardrails via ``GuardrailChain``.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from pyarnes_core.errors import UserFixableError
from pyarnes_core.observe.logger import get_logger

__all__ = [
    "CommandGuardrail",
    "Guardrail",
    "GuardrailChain",
    "PathGuardrail",
    "ToolAllowlistGuardrail",
]

logger = get_logger(__name__)


class Guardrail(ABC):
    """Abstract base for a single guardrail check.

    Subclass and implement :meth:`check` to create a concrete guardrail.
    The method must raise ``UserFixableError`` if the call violates the
    guardrail, or return ``None`` silently if it passes.
    """

    @abstractmethod
    def check(self, tool_name: str, arguments: dict[str, Any]) -> None:
        """Raise ``UserFixableError`` if the call violates this guardrail.

        Args:
            tool_name: The name of the tool being invoked.
            arguments: Key-value arguments passed to the tool.
        """


# ── Concrete guardrails ───────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class PathGuardrail(Guardrail):
    """Block tool calls that reference paths outside an allowed set.

    Attributes:
        allowed_roots: Directory prefixes that tools may access.
        path_keys: Argument keys that are expected to contain file paths.
    """

    allowed_roots: tuple[str, ...] = ("/workspace",)
    path_keys: tuple[str, ...] = ("path", "file", "directory", "target")

    def check(self, tool_name: str, arguments: dict[str, Any]) -> None:
        """Validate that all path arguments fall under allowed roots."""
        for key in self.path_keys:
            value = arguments.get(key)
            if value is None:
                continue
            resolved = str(PurePosixPath(value))
            if not any(resolved.startswith(root) for root in self.allowed_roots):
                logger.warning("guardrail.path_blocked tool={tool} path={path}", tool=tool_name, path=resolved)
                raise UserFixableError(
                    message=f"Path '{resolved}' is outside allowed roots {self.allowed_roots}",
                    prompt_hint=f"Allow access to '{resolved}'?",
                )


@dataclass(frozen=True, slots=True)
class CommandGuardrail(Guardrail):
    """Block shell commands matching dangerous patterns.

    Attributes:
        blocked_patterns: Regex patterns that should never appear in a command string.
    """

    blocked_patterns: tuple[str, ...] = (
        r"\brm\s+-rf\s+/",
        r"\bsudo\b",
        r"\bchmod\s+777\b",
        r"\bcurl\b.*\|\s*(ba)?sh",
    )

    def check(self, tool_name: str, arguments: dict[str, Any]) -> None:
        """Reject commands matching any blocked pattern."""
        cmd = arguments.get("command", "")
        if not isinstance(cmd, str):
            return
        for pattern in self.blocked_patterns:
            if re.search(pattern, cmd):
                logger.warning(
                    "guardrail.command_blocked tool={tool} pattern={pattern}",
                    tool=tool_name,
                    pattern=pattern,
                )
                raise UserFixableError(
                    message=f"Command blocked by pattern: {pattern}",
                    prompt_hint="Review and approve this command manually.",
                )


@dataclass(frozen=True, slots=True)
class ToolAllowlistGuardrail(Guardrail):
    """Only permit a pre-approved set of tool names.

    Attributes:
        allowed_tools: Set of tool names the harness may invoke.
    """

    allowed_tools: frozenset[str] = frozenset()

    def check(self, tool_name: str, arguments: dict[str, Any]) -> None:  # noqa: ARG002
        """Reject calls to tools not on the allowlist."""
        if self.allowed_tools and tool_name not in self.allowed_tools:
            logger.warning("guardrail.tool_not_allowed tool={tool}", tool=tool_name)
            raise UserFixableError(
                message=f"Tool '{tool_name}' is not in the allowlist",
                prompt_hint=f"Add '{tool_name}' to the allowed tools?",
            )


# ── Chain ──────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class GuardrailChain:
    """Run a sequence of guardrails; fail on the first violation.

    Attributes:
        guardrails: Ordered list of guardrails to evaluate.
    """

    guardrails: list[Guardrail] = field(default_factory=list)

    def check(self, tool_name: str, arguments: dict[str, Any]) -> None:
        """Run every guardrail in order.

        Args:
            tool_name: The name of the tool being invoked.
            arguments: Key-value arguments passed to the tool.
        """
        for guardrail in self.guardrails:
            guardrail.check(tool_name, arguments)
