"""Walk a project root and build the audit graph."""

from __future__ import annotations

import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import networkx as nx

from pyarnes_bench.audit.config import AuditConfig
from pyarnes_bench.audit.events import log_audit_indexed
from pyarnes_bench.audit.parser import PythonParser
from pyarnes_bench.audit.schema import Edge, Node
from pyarnes_core.observability import iso_now
from pyarnes_core.observability.ports import LoggerPort

__all__ = ["build_graph", "iter_python_files"]


def iter_python_files(root: Path, *, exclude: Iterable[str]) -> Iterable[Path]:
    """Yield ``.py`` files under *root* skipping *exclude* path fragments.

    The filter is intentionally a substring check on the resolved path —
    it catches both top-level dirs (``.venv``) and nested ones
    (``packages/foo/.pyarnes``) without needing globbing.
    """
    excludes = tuple(exclude)
    for path in root.rglob("*.py"):
        rel = str(path)
        if any(f"/{e}/" in rel or rel.endswith(f"/{e}") or rel.startswith(f"{e}/") for e in excludes):
            continue
        yield path


def build_graph(  # noqa: PLR0913
    *,
    config: AuditConfig,
    logger: LoggerPort,
    session_id: str,
    trace_id: str,
    step: int,
    parser: PythonParser | None = None,
) -> nx.DiGraph:
    """Walk every configured root and return a populated ``nx.DiGraph``.

    Args:
        config: Audit configuration (project root, roots to scan, exclusions).
        logger: Where ``audit.indexed`` lands.
        session_id: Session identifier propagated to every event.
        trace_id: Trace identifier for distributed tracing.
        step: Current step number used for event ordering.
        parser: Optional pre-built :class:`PythonParser` (mostly for tests).

    Returns:
        A directed graph whose nodes carry the dataclass fields as attributes
        and whose edges carry ``kind`` / ``file_path`` / ``line`` attributes.
    """
    parser = parser or PythonParser()
    graph: nx.DiGraph = nx.DiGraph()
    started = iso_now()
    started_mono = time.monotonic()
    files = 0

    for root_str in config.roots:
        root = (config.project_root / root_str).resolve()
        if not root.is_dir():
            continue
        for path in iter_python_files(root, exclude=config.exclude):
            try:
                nodes, edges = parser.parse_file(path, project_root=config.project_root)
            except Exception:  # noqa: S112  # best-effort parse: a single bad file must not tank the whole audit
                continue
            files += 1
            _add_nodes(graph, nodes)
            _add_edges(graph, edges)

    _resolve_imports(graph)

    duration_ms = (time.monotonic() - started_mono) * 1000.0
    log_audit_indexed(
        logger,
        str(config.project_root),
        files=files,
        nodes=graph.number_of_nodes(),
        edges=graph.number_of_edges(),
        duration_ms=duration_ms,
        session_id=session_id,
        trace_id=trace_id,
        step=step,
    )
    graph.graph["indexed_at"] = started
    graph.graph["files"] = files
    return graph


def _add_nodes(graph: nx.DiGraph, nodes: list[Node]) -> None:
    for n in nodes:
        graph.add_node(
            n.id,
            kind=str(n.kind),
            name=n.name,
            file_path=n.file_path,
            line_start=n.line_start,
            line_end=n.line_end,
            qualname=n.qualname,
            extra=n.extra,
        )


def _add_edges(graph: nx.DiGraph, edges: list[Edge]) -> None:
    for e in edges:
        graph.add_edge(
            e.src,
            e.dst,
            kind=str(e.kind),
            file_path=e.file_path,
            line=e.line,
            extra=e.extra,
        )


def _resolve_imports(graph: nx.DiGraph) -> None:  # noqa: C901  # orchestration layer; readable as one pass
    """Rewrite import edges to point at module nodes by qualname.

    The parser emits IMPORTS / IMPORTS_FROM edges with the imported name as
    the destination string (``"pkg.b"``, ``"pkg.b.x"``). Cycle detection and
    unused-file detection both need those edges to resolve to actual module
    node ids when the target is a known module in this project. We collect
    the qualname → node-id map from the MODULE nodes, then for each import
    edge whose destination string is (or starts with) a known qualname, drop
    the unresolved edge and add the resolved one in its place.
    """
    qual_to_id: dict[str, str] = {}
    for node_id, attrs in graph.nodes(data=True):
        if attrs.get("kind") == "module":
            qualname = attrs.get("qualname", "")
            if qualname:
                qual_to_id[qualname] = node_id

    if not qual_to_id:
        return

    rewrites: list[tuple[str, str, str, dict[str, Any]]] = []
    for src, dst, attrs in graph.edges(data=True):
        if attrs.get("kind") not in {"imports", "imports_from"}:
            continue
        target = str(dst)
        if target in qual_to_id:
            rewrites.append((src, dst, qual_to_id[target], dict(attrs)))
            continue
        # `from pkg.b import x` lands as `pkg.b.x` — strip the trailing name
        # if the parent qualname is a known module.
        if "." in target:
            head = target.rsplit(".", 1)[0]
            if head in qual_to_id:
                rewrites.append((src, dst, qual_to_id[head], dict(attrs)))

    for src, old_dst, new_dst, attrs in rewrites:
        if graph.has_edge(src, old_dst):
            graph.remove_edge(src, old_dst)
        graph.add_edge(src, new_dst, **attrs)
