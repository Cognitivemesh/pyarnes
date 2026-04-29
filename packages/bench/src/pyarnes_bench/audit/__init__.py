"""``pyarnes_bench.audit`` — code-graph + audit subpackage.

LLM-free, Python-only, in-tree replacement for ``graphify`` and
``code-review-graph``. Phase 1 ships a tree-sitter-python parser, an
``nx.DiGraph`` graph, JSON persistence, three structural analyses, and eight
detectors. Phase 2 (deferred) adds opt-in extras for libsql persistence,
Leiden communities, Jinja2 reports, and an MCP server entrypoint inside the
same subpackage.
"""

from __future__ import annotations

from pyarnes_bench.audit.analyze import (
    god_nodes,
    suggested_questions,
    surprising_connections,
)
from pyarnes_bench.audit.audit import audit_graph
from pyarnes_bench.audit.boundaries import check_boundaries
from pyarnes_bench.audit.builder import build_graph, iter_python_files
from pyarnes_bench.audit.config import AuditConfig
from pyarnes_bench.audit.duplicates import detect_duplicates
from pyarnes_bench.audit.events import (
    log_audit_analyzed,
    log_audit_finding,
    log_audit_indexed,
)
from pyarnes_bench.audit.findings import Finding, FindingSummary, summarize
from pyarnes_bench.audit.parser import PythonParser
from pyarnes_bench.audit.schema import Edge, EdgeKind, Node, NodeKind, make_node_id
from pyarnes_bench.audit.store import load_graph, save_graph

__all__ = [
    "AuditConfig",
    "Edge",
    "EdgeKind",
    "Finding",
    "FindingSummary",
    "Node",
    "NodeKind",
    "PythonParser",
    "audit_graph",
    "build_graph",
    "check_boundaries",
    "detect_duplicates",
    "god_nodes",
    "iter_python_files",
    "load_graph",
    "log_audit_analyzed",
    "log_audit_finding",
    "log_audit_indexed",
    "make_node_id",
    "save_graph",
    "suggested_questions",
    "summarize",
    "surprising_connections",
]
