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

    # Deep mode adds network-call detection via libcst (if installed)
    findings = analyse_code(source, deep=True)
"""

from __future__ import annotations

import ast
import functools
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

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

# Additional patterns detected only in deep mode (requires libcst).
DEEP_BANNED_CALLS: frozenset[str] = frozenset(
    {
        "socket.socket",
        "socket.create_connection",
        "urllib.request.urlopen",
        "urllib.request.Request",
        "httpx.get",
        "httpx.post",
        "httpx.put",
        "httpx.delete",
        "httpx.patch",
        "httpx.head",
        "httpx.request",
        "httpx.Client",
        "httpx.AsyncClient",
    }
)

DEEP_BANNED_IMPORTS: frozenset[str] = frozenset(
    {
        "socket",
        "urllib",
        "httpx",
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

    kind: Literal["import", "call"]
    symbol: str
    lineno: int
    col_offset: int


def analyse_code(
    source: str,
    *,
    banned_imports: frozenset[str] = BANNED_IMPORTS,
    banned_calls: frozenset[str] = BANNED_CALLS,
    deep: bool = False,
) -> list[Finding]:
    """Parse *source* as Python and return all dangerous-pattern findings.

    Silently returns an empty list when *source* is not valid Python (so
    guardrails that run on general text arguments do not break on non-code
    strings).

    Args:
        source: Python source code to analyse.
        banned_imports: Root module names whose import is a finding.
        banned_calls: Call names (bare or dotted) whose use is a finding.
        deep: When ``True``, run an additional libcst-based pass that detects
            network calls (``socket``, ``urllib``, ``httpx``) and more. Falls
            back to the standard analysis when libcst is not installed.

    Returns:
        A list of :class:`Finding` instances, possibly empty.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    visitor = _Visitor(banned_imports=banned_imports, banned_calls=banned_calls)
    visitor.visit(tree)
    findings = visitor.findings

    if deep:
        findings = findings + _analyse_code_deep(
            source,
            extra_banned_calls=DEEP_BANNED_CALLS,
            extra_banned_imports=DEEP_BANNED_IMPORTS,
        )

    return findings


def scan_code_arguments(  # noqa: PLR0913
    arguments: dict[str, Any],
    *,
    keys: Iterable[str],
    tool_name: str,
    banned_imports: frozenset[str] = BANNED_IMPORTS,
    banned_calls: frozenset[str] = BANNED_CALLS,
    deep: bool = False,
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
        deep: When ``True``, also run deep (libcst) analysis.

    Raises:
        LLMRecoverableError: On the first dangerous pattern found.
    """
    for raw in walk_values_for_keys(arguments, keys):
        for candidate in walk_strings(raw):
            findings = analyse_code(
                candidate,
                banned_imports=banned_imports,
                banned_calls=banned_calls,
                deep=deep,
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
            if _root_module(alias.name) in self._banned_imports:
                self.findings.append(Finding("import", alias.name, node.lineno, node.col_offset))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module and _root_module(node.module) in self._banned_imports:
            self.findings.append(Finding("import", node.module, node.lineno, node.col_offset))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = _dotted_name(node.func)
        if name in self._banned_calls:
            self.findings.append(Finding("call", name, node.lineno, node.col_offset))
        self.generic_visit(node)


def _root_module(dotted: str) -> str:
    return dotted.split(".", maxsplit=1)[0]


def _dotted_name(node: ast.expr) -> str:
    """Reconstruct a dotted name from a Name or chained Attribute node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


# ── libcst deep analysis ─────────────────────────────────────────────────────


@functools.lru_cache(maxsize=256)
def _try_parse_cst(source: str) -> Any:
    """Parse *source* with libcst and return the module; returns ``None`` on failure.

    The result is cached by source string so repeated analysis of the
    same snippet pays the parse cost only once.
    """
    try:
        import libcst as cst  # noqa: PLC0415

        return cst.parse_module(source)
    except Exception:
        return None


def _libcst_dotted_name(node: Any) -> str:
    """Reconstruct a dotted name from a libcst Name or Attribute node."""
    try:
        import libcst as cst  # noqa: PLC0415

        if isinstance(node, cst.Name):
            return node.value
        if isinstance(node, cst.Attribute):
            prefix = _libcst_dotted_name(node.value)
            return f"{prefix}.{node.attr.value}" if prefix else node.attr.value
    except ImportError:
        pass
    return ""


def _analyse_code_deep(  # noqa: C901
    source: str,
    extra_banned_calls: frozenset[str],
    extra_banned_imports: frozenset[str],
) -> list[Finding]:
    """Deep analysis via libcst; returns ``[]`` when libcst is not installed."""
    try:
        import libcst as cst  # noqa: PLC0415
        from libcst.metadata import MetadataWrapper, PositionProvider  # noqa: PLC0415
    except ImportError:
        return []

    module = _try_parse_cst(source)
    if module is None:
        return []

    try:
        wrapper = MetadataWrapper(module)
    except Exception:
        return []

    findings: list[Finding] = []

    class _LibCSTVisitor(cst.CSTVisitor):
        METADATA_DEPENDENCIES = (PositionProvider,)

        def visit_Import(self, node: cst.Import) -> None:  # noqa: N802  # type: ignore[override]
            if isinstance(node.names, cst.ImportStar):
                return
            for alias in node.names:
                name = _libcst_dotted_name(alias.name)
                if _root_module(name) in extra_banned_imports:
                    try:
                        pos = self.get_metadata(PositionProvider, node)
                        lineno, col = pos.start.line, pos.start.column
                    except Exception:
                        lineno, col = 0, 0
                    findings.append(Finding("import", name, lineno, col))

        def visit_ImportFrom(self, node: cst.ImportFrom) -> None:  # noqa: N802  # type: ignore[override]
            if node.module is not None:
                name = _libcst_dotted_name(node.module)
                if _root_module(name) in extra_banned_imports:
                    try:
                        pos = self.get_metadata(PositionProvider, node)
                        lineno, col = pos.start.line, pos.start.column
                    except Exception:
                        lineno, col = 0, 0
                    findings.append(Finding("import", name, lineno, col))

        def visit_Call(self, node: cst.Call) -> None:  # noqa: N802  # type: ignore[override]
            name = _libcst_dotted_name(node.func)
            if name in extra_banned_calls:
                try:
                    pos = self.get_metadata(PositionProvider, node)
                    lineno, col = pos.start.line, pos.start.column
                except Exception:
                    lineno, col = 0, 0
                findings.append(Finding("call", name, lineno, col))

    try:
        wrapper.visit(_LibCSTVisitor())
    except Exception:
        return []
    return findings
