"""Architecture-boundary checking.

Forbidden edges live in ``[tool.pyarnes-audit].forbidden_edges`` as
``[upstream, downstream]`` pairs. Any IMPORTS / IMPORTS_FROM edge whose source
file lives under ``upstream`` and whose target name starts with ``downstream``
is reported.
"""

from __future__ import annotations

from collections.abc import Iterable

import networkx as nx

from pyarnes_bench.audit.findings import Finding
from pyarnes_bench.audit.schema import EdgeKind

__all__ = ["check_boundaries"]

_IMPORT_EDGE_KINDS = {EdgeKind.IMPORTS.value, EdgeKind.IMPORTS_FROM.value}


def _src_module(graph: nx.DiGraph, src_id: str) -> str:
    return str(graph.nodes[src_id].get("qualname", ""))


def _is_violation(src_module: str, target_name: str, upstream: str, downstream: str) -> bool:
    # The forbidden direction is "upstream must not import from downstream".
    return src_module.startswith(upstream) and target_name.startswith(downstream)


def check_boundaries(
    graph: nx.DiGraph,
    *,
    forbidden_edges: Iterable[tuple[str, str]],
) -> list[Finding]:
    """Return one HIGH finding per imported edge that crosses a forbidden boundary."""
    rules = list(forbidden_edges)
    if not rules:
        return []
    findings: list[Finding] = []
    for src, dst, attrs in graph.edges(data=True):
        if attrs.get("kind") not in _IMPORT_EDGE_KINDS:
            continue
        src_module = _src_module(graph, src)
        target = str(dst)
        for upstream, downstream in rules:
            if _is_violation(src_module, target, upstream, downstream):
                findings.append(
                    Finding(
                        category="boundary_violation",
                        target=src,
                        severity="high",
                        detail={
                            "src_module": src_module,
                            "imported": target,
                            "rule": [upstream, downstream],
                        },
                    )
                )
                break
    return findings
