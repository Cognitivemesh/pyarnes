"""Safety guardrails for the agentic harness.

Guardrails wrap tool execution and enforce limits on what the system
can touch. They are composable — stack multiple guardrails via
``GuardrailChain``. The concrete checks delegate to molecules under
``pyarnes_core.safety.molecules`` so that the path-containment and
command-scan logic lives in one tested location.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pyarnes_core.errors import UserFixableError
from pyarnes_core.observability import log_warning
from pyarnes_core.observe.logger import get_logger
from pyarnes_core.safety import (
    assert_within_roots,
    has_traversal,
    scan_code_arguments,
    scan_for_patterns,
    walk_strings,
    walk_values_for_keys,
)

__all__ = [
    "ASTGuardrail",
    "AsyncGuardrail",
    "CommandGuardrail",
    "Guardrail",
    "GuardrailChain",
    "PathGuardrail",
    "ToolAllowlistGuardrail",
]

logger = get_logger(__name__)


class Guardrail(ABC):
    """Abstract base for a synchronous guardrail check.

    Subclass and implement :meth:`check` to create a concrete guardrail.
    The method must raise ``UserFixableError`` if the call violates the
    guardrail, or return ``None`` silently if it passes.

    For guardrails that require async I/O (e.g. LLM judge calls),
    use :class:`AsyncGuardrail` instead.
    """

    @abstractmethod
    def check(self, tool_name: str, arguments: dict[str, Any]) -> None:
        """Raise ``UserFixableError`` if the call violates this guardrail.

        Args:
            tool_name: The name of the tool being invoked.
            arguments: Key-value arguments passed to the tool.
        """


class AsyncGuardrail(ABC):
    """Abstract base for guardrails that require async I/O.

    Use this for guardrails that must ``await`` an external call, e.g.
    an LLM judge. :class:`GuardrailChain` dispatches both
    ``Guardrail`` and ``AsyncGuardrail`` instances correctly.
    """

    @abstractmethod
    async def check(self, tool_name: str, arguments: dict[str, Any]) -> None:
        """Raise an error if the call violates this guardrail.

        Args:
            tool_name: The name of the tool being invoked.
            arguments: Key-value arguments passed to the tool.
        """


# ── Concrete guardrails ───────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class PathGuardrail(Guardrail):
    """Block tool calls that reference paths outside an allowed set.

    By default (``resolve_symlinks=False``), checks are lexical only:
    ``Path.parts`` prefix comparison is used without filesystem resolution.
    This means symlinks inside allowed roots can still point outside them —
    a potential sandbox-escape risk in security-sensitive deployments. Set
    ``resolve_symlinks=True`` to enforce canonical path resolution and block
    symlink escapes. Nested and list-valued path arguments are walked
    recursively.

    Attributes:
        allowed_roots: Directory prefixes that tools may access.
        path_keys: Argument keys that are expected to contain file paths.
        resolve_symlinks: Whether to resolve symlinks before containment checks.
            Defaults to ``False`` for backward compatibility.
    """

    allowed_roots: tuple[str, ...] = ("/workspace",)
    path_keys: tuple[str, ...] = ("path", "file", "directory", "target")
    resolve_symlinks: bool = False

    def check(self, tool_name: str, arguments: dict[str, Any]) -> None:
        """Validate that every path argument falls under allowed roots."""
        for raw in walk_values_for_keys(arguments, keys=self.path_keys):
            for candidate in walk_strings(raw):
                try:
                    if self.resolve_symlinks:
                        assert_within_roots(candidate, self.allowed_roots)
                    else:
                        # Lexical-only mode is backward compatible but does
                        # not prevent symlink escapes from allowed roots.
                        self._assert_within_roots_lexical(candidate)
                except UserFixableError:
                    log_warning(
                        logger,
                        "guardrail.path_blocked",
                        tool=tool_name,
                        path=candidate,
                    )
                    raise

    def _assert_within_roots_lexical(self, path: str) -> None:
        """Check containment lexically without following symlinks."""
        roots_tuple = tuple(self.allowed_roots)
        if has_traversal(path):
            raise UserFixableError(
                message=f"Path '{path}' contains a traversal segment",
                prompt_hint=f"Provide an absolute path under {roots_tuple}",
            )

        path_parts = Path(path).parts
        if not path_parts:
            raise UserFixableError(
                message=f"Path '{path}' is empty or invalid",
                prompt_hint=f"Allow access to '{path}'?",
            )
        root_parts_list = tuple(Path(root).parts for root in roots_tuple)
        for root_parts in root_parts_list:
            if path_parts[: len(root_parts)] == root_parts:
                return

        raise UserFixableError(
            message=f"Path '{path}' is outside allowed roots {roots_tuple}",
            prompt_hint=f"Allow access to '{path}'?",
        )


@dataclass(frozen=True, slots=True)
class CommandGuardrail(Guardrail):
    """Block shell commands matching dangerous patterns.

    Scans every argument key named in :attr:`command_keys`, including
    list-of-argv shapes (joined with single spaces) and nested dicts,
    so tools with alternate schemas (``cmd``, ``argv``, ``script``, …)
    are covered.

    Attributes:
        blocked_patterns: Regex patterns that should never appear in a command string.
        command_keys: Argument keys expected to carry command text.
    """

    blocked_patterns: tuple[str, ...] = (
        r"\brm\s+-rf\s+/",
        r"\bsudo\b",
        r"\bchmod\s+777\b",
        r"\bcurl\b.*\|\s*(ba)?sh",
    )
    command_keys: tuple[str, ...] = (
        "command",
        "cmd",
        "argv",
        "script",
        "shell_command",
        "run",
    )

    def check(self, tool_name: str, arguments: dict[str, Any]) -> None:
        """Reject commands matching any blocked pattern."""
        try:
            scan_for_patterns(
                arguments,
                keys=self.command_keys,
                patterns=self.blocked_patterns,
                tool_name=tool_name,
            )
        except UserFixableError:
            log_warning(logger, "guardrail.command_blocked", tool=tool_name)
            raise


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
            log_warning(logger, "guardrail.tool_not_allowed", tool=tool_name)
            raise UserFixableError(
                message=f"Tool '{tool_name}' is not in the allowlist",
                prompt_hint=f"Add '{tool_name}' to the allowed tools?",
            )


@dataclass(frozen=True, slots=True)
class ASTGuardrail(Guardrail):
    """Block tool calls whose code arguments contain dangerous AST patterns.

    Runs :func:`pyarnes_core.safety.scan_code_arguments` on the arguments
    specified in *code_keys*. When *deep* is ``True`` (the default) and
    ``libcst`` is installed (soft dep: ``pip install libcst>=1.0``), the
    analysis also detects ``socket``, ``urllib``, and ``httpx`` network calls.
    Degrades to the standard ast-based analysis when libcst is absent.

    Attributes:
        deep: Enable libcst-powered deep analysis. Default ``True``.
        code_keys: Argument keys expected to contain Python source code.
    """

    deep: bool = True
    code_keys: tuple[str, ...] = ("code", "script", "source")

    def check(self, tool_name: str, arguments: dict[str, Any]) -> None:
        """Raise ``LLMRecoverableError`` when a code argument contains a banned pattern."""
        try:
            scan_code_arguments(arguments, keys=self.code_keys, tool_name=tool_name, deep=self.deep)
        except Exception:
            log_warning(logger, "guardrail.ast_blocked", tool=tool_name)
            raise


# ── Chain ──────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class GuardrailChain:
    """Run a sequence of guardrails; fail on the first violation.

    Accepts both :class:`Guardrail` (sync) and :class:`AsyncGuardrail`
    members in the same list. Sync members are called directly; async
    members are awaited.

    Attributes:
        guardrails: Ordered list of guardrails to evaluate.
    """

    guardrails: list[Guardrail | AsyncGuardrail] = field(default_factory=list)

    async def check(self, tool_name: str, arguments: dict[str, Any]) -> None:
        """Run every guardrail in order.

        Args:
            tool_name: The name of the tool being invoked.
            arguments: Key-value arguments passed to the tool.
        """
        for guardrail in self.guardrails:
            if isinstance(guardrail, AsyncGuardrail):
                await guardrail.check(tool_name, arguments)
            else:
                guardrail.check(tool_name, arguments)
