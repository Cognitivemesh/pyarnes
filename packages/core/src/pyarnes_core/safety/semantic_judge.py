"""Atom: AST-based semantic analysis — detect dangerous import and call patterns.

Pattern matching (``command_scan``) works on raw strings; AST analysis operates on
the parsed program structure so code cannot bypass checks with whitespace tricks or
string concatenation that regex misses.

Usage::

    from pyarnes_core.safety import analyse_code, scan_code_arguments

    findings = analyse_code(source)
    for f in findings:
        print(f.kind, f.symbol, f.lineno)

    # Molecule-style: raises LLMRecoverableError on any finding
    scan_code_arguments(arguments, keys=("code", "source"), tool_name="execute_code")
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from pyarnes_core.errors import LLMRecoverableError
from pyarnes_core.safety.arg_walker import walk_strings, walk_values_for_keys

__all__ = [
    "Finding",
    "analyse_code",
    "scan_code_arguments",
]

BANNED_IMPORTS: frozenset[str] = frozenset(
    {
        "subprocess",
        "ctypes",
        "importlib",
    }
)

BANNED_CALLS: frozenset[str] = frozenset(
    {
        "eval",
        "exec",
        "compile",
        "__import__",
        "os.system",
        "os.popen",
    }
)


@dataclass(frozen=True, slots=True)
class Finding:
    """A single dangerous pattern detected during AST analysis.

    Attributes:
        kind: ``"import"`` or ``"call"``.
        symbol: The module or callable name that triggered the finding.
        lineno: Source line number (1-indexed).
        col_offset: Column offset (0-indexed).
    """

    kind: str
    symbol: str
    lineno: int
    col_offset: int


def analyse_code(
    source: str,
    *,
    banned_imports: frozenset[str] = BANNED_IMPORTS,
    banned_calls: frozenset[str] = BANNED_CALLS,
) -> list[Finding]:
    """Parse *source* as Python and return all dangerous-pattern findings.

    Silently returns an empty list when *source* is not valid Python (so
    guardrails that run on general text arguments do not break on non-code
    strings).

    Args:
        source: Python source code to analyse.
        banned_imports: Root module names whose import is a finding.
        banned_calls: Call names (bare or dotted) whose use is a finding.

    Returns:
        A list of :class:`Finding` instances, possibly empty.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    visitor = _Visitor(banned_imports=banned_imports, banned_calls=banned_calls)
    visitor.visit(tree)
    return visitor.findings


def scan_code_arguments(
    arguments: dict[str, Any],
    *,
    keys: Iterable[str],
    tool_name: str,
    banned_imports: frozenset[str] = BANNED_IMPORTS,
    banned_calls: frozenset[str] = BANNED_CALLS,
) -> None:
    """Raise ``LLMRecoverableError`` when any code argument contains dangerous patterns.

    Collects every string reachable under any key in *keys*, runs
    :func:`analyse_code` on each, and raises on the first finding so the
    agent loop feeds the violation back to the model as a ``ToolMessage``.

    Args:
        arguments: The tool's argument dict.
        keys: Argument keys whose values should be treated as Python source.
        tool_name: Used in the error message.
        banned_imports: Forwarded to :func:`analyse_code`.
        banned_calls: Forwarded to :func:`analyse_code`.

    Raises:
        LLMRecoverableError: On the first dangerous pattern found.
    """
    for raw in walk_values_for_keys(arguments, keys):
        for candidate in walk_strings(raw):
            findings = analyse_code(
                candidate,
                banned_imports=banned_imports,
                banned_calls=banned_calls,
            )
            if findings:
                f = findings[0]
                raise LLMRecoverableError(
                    message=(
                        f"Tool '{tool_name}' code argument contains a banned {f.kind}: "
                        f"'{f.symbol}' at line {f.lineno}. "
                        "Rewrite without dynamic execution or prohibited imports."
                    ),
                )


# ── Internal ────────────────────────────────────────────────────────────────


class _Visitor(ast.NodeVisitor):
    def __init__(
        self,
        *,
        banned_imports: frozenset[str],
        banned_calls: frozenset[str],
    ) -> None:
        self.findings: list[Finding] = []
        self._banned_imports = banned_imports
        self._banned_calls = banned_calls

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root = alias.name.split(".")[0]
            if root in self._banned_imports:
                self.findings.append(
                    Finding("import", alias.name, node.lineno, node.col_offset)
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            root = node.module.split(".")[0]
            if root in self._banned_imports:
                self.findings.append(
                    Finding("import", node.module, node.lineno, node.col_offset)
                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = _dotted_name(node.func)
        if name in self._banned_calls:
            self.findings.append(Finding("call", name, node.lineno, node.col_offset))
        self.generic_visit(node)


def _dotted_name(node: ast.expr) -> str:
    """Reconstruct a dotted name from a Name or chained Attribute node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""
