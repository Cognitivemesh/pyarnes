"""Function-body duplicate detection via AST normalisation.

Algorithm:

1. Parse each FUNCTION/METHOD node's body (already captured in ``extra.body``
   by the parser) with the stdlib :mod:`ast` module.
2. Strip the docstring, then re-emit the body via ``ast.unparse(ast.parse(...))``
   so whitespace, comments, and trailing blank lines are normalised away.
3. Hash the normalised body. Group nodes by hash; any group with more than one
   member where the body is at least ``min_tokens`` long is reported.

The token threshold uses the shared :func:`estimate_tokens` helper so the
floor is consistent with every other ``// 4`` heuristic in the repo.
"""

from __future__ import annotations

import ast
import hashlib
from collections import defaultdict

import networkx as nx

from pyarnes_bench.audit.findings import Finding
from pyarnes_core.observability import estimate_tokens

__all__ = ["detect_duplicates"]


def _normalised_body(body: str) -> str | None:
    """Return a canonicalised representation of *body*, or ``None`` if invalid."""
    try:
        tree = ast.parse(body)
    except SyntaxError:
        return None
    if not tree.body:
        return None
    func = tree.body[0]
    if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
        # Body that doesn't start with a def — bail rather than guess.
        return None
    # Drop the docstring (first stmt if it's an expression of a string literal).
    if (
        func.body
        and isinstance(func.body[0], ast.Expr)
        and isinstance(func.body[0].value, ast.Constant)
        and isinstance(func.body[0].value.value, str)
    ):
        func.body = func.body[1:]
    if not func.body:
        return None
    return ast.unparse(ast.Module(body=func.body, type_ignores=[]))


def _hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def detect_duplicates(graph: nx.DiGraph, *, min_tokens: int) -> list[Finding]:
    """Return MEDIUM findings for function bodies that share a normalised hash."""
    by_hash: dict[str, list[str]] = defaultdict(list)
    for node_id, attrs in graph.nodes(data=True):
        if attrs.get("kind") not in {"function", "method"}:
            continue
        body = attrs.get("extra", {}).get("body")
        if not isinstance(body, str):
            continue
        normalised = _normalised_body(body)
        if normalised is None:
            continue
        if estimate_tokens(normalised) < min_tokens:
            continue
        by_hash[_hash(normalised)].append(node_id)

    findings: list[Finding] = []
    for digest, ids in by_hash.items():
        if len(ids) < 2:  # noqa: PLR2004  # need ≥2 nodes for a duplicate group
            continue
        # Report once per duplicate group keyed by the first id; the rest of
        # the group is in `detail.duplicates` so a fixer knows what to merge.
        primary, *rest = sorted(ids)
        findings.append(
            Finding(
                category="duplicate_block",
                target=primary,
                severity="medium",
                detail={"hash": digest, "duplicates": rest, "group_size": len(ids)},
            )
        )
    return findings
