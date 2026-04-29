"""Detector orchestrator — ``audit_graph`` returns a flat list of findings.

Detectors that need only the graph (unused files, circular imports, duplicate
blocks, boundary violations) run inline. Detectors that need extra signal
(``vulture`` for unused exports, ``radon`` for complexity, regex for feature
flags, ``pyproject.toml`` for unused deps) shell out where the existing
binary already does the analysis better than we would re-implement it.
"""

from __future__ import annotations

import json
import re
import subprocess  # nosec B404
import sys
import tomllib
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

import networkx as nx

from pyarnes_bench.audit.boundaries import check_boundaries
from pyarnes_bench.audit.config import AuditConfig
from pyarnes_bench.audit.duplicates import detect_duplicates
from pyarnes_bench.audit.events import log_audit_finding
from pyarnes_core.observability.ports import LoggerPort

from pyarnes_bench.audit.findings import Finding

__all__ = ["audit_graph"]


def audit_graph(  # noqa: PLR0913
    graph: nx.DiGraph,
    *,
    config: AuditConfig,
    logger: LoggerPort,
    session_id: str,
    trace_id: str,
    step: int,
) -> list[Finding]:
    """Run every detector and return the union of findings.

    Each finding is also emitted via ``log_audit_finding`` so the JSONL stderr
    stream sees the same data the CLI prints to stdout.
    """
    findings: list[Finding] = []
    findings.extend(_unused_files(graph))
    findings.extend(_circular_imports(graph))
    findings.extend(detect_duplicates(graph, min_tokens=config.duplicate_min_tokens))
    findings.extend(check_boundaries(graph, forbidden_edges=config.forbidden_edges))
    findings.extend(_complexity_hotspots(config))
    findings.extend(_unused_exports(graph, config))
    findings.extend(_unused_dependencies(graph, config))
    findings.extend(_feature_flag_usage(graph, config))

    for f in findings:
        log_audit_finding(
            logger,
            f.category,
            f.target,
            f.severity,
            session_id=session_id,
            trace_id=trace_id,
            step=step,
            detail=f.detail,
        )
    return findings


# ── Detectors ─────────────────────────────────────────────────────────────


def _unused_files(graph: nx.DiGraph) -> list[Finding]:
    """Module nodes with zero inbound import edges from the rest of the project.

    The builder's link pass rewrites import-edge destinations to module node
    ids when the target qualname matches a project module. So a module that
    has at least one inbound IMPORTS / IMPORTS_FROM edge here is genuinely
    used by another file in the project; one with none is a candidate for
    removal (modulo CLI entry points, which look identical to imports' eyes).
    """
    findings: list[Finding] = []
    for node_id, attrs in graph.nodes(data=True):
        if attrs.get("kind") != "module":
            continue
        if not _has_inbound_import(graph, node_id):
            findings.append(
                Finding(
                    category="unused_file",
                    target=node_id,
                    severity="low",
                    detail={
                        "qualname": attrs.get("qualname", ""),
                        "file_path": attrs.get("file_path", ""),
                    },
                )
            )
    return findings


def _has_inbound_import(graph: nx.DiGraph, node_id: str) -> bool:
    for _src, _dst, attrs in graph.in_edges(node_id, data=True):
        if attrs.get("kind") in {"imports", "imports_from"}:
            return True
    return False


def _circular_imports(graph: nx.DiGraph) -> list[Finding]:
    import_subgraph = nx.DiGraph(
        (u, v) for u, v, attrs in graph.edges(data=True) if attrs.get("kind") in {"imports", "imports_from"}
    )
    cycles = list(nx.simple_cycles(import_subgraph))
    findings: list[Finding] = []
    for cycle in cycles:
        if len(cycle) < 2:
            continue
        findings.append(
            Finding(
                category="circular_import",
                target=cycle[0],
                severity="high",
                detail={"cycle": cycle},
            )
        )
    return findings


def _complexity_hotspots(config: AuditConfig) -> list[Finding]:
    cmd = [sys.executable, "-m", "radon", "cc", "--min", "C", "--json", *config.roots]
    try:
        result = subprocess.run(  # nosec B603
            cmd,
            cwd=str(config.project_root),
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return []
    if not result.stdout.strip():
        return []
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    findings: list[Finding] = []
    for file_path, entries in data.items():
        for entry in entries:
            rank = entry.get("rank", "")
            if rank not in {"C", "D", "E", "F"}:
                continue
            severity = "high" if rank in {"D", "E", "F"} else "medium"
            findings.append(
                Finding(
                    category="complexity_hotspot",
                    target=f"{file_path}::{entry.get('name', '?')}",
                    severity=severity,
                    detail={
                        "rank": rank,
                        "complexity": entry.get("complexity"),
                        "lineno": entry.get("lineno"),
                    },
                )
            )
    return findings


def _unused_exports(graph: nx.DiGraph, config: AuditConfig) -> list[Finding]:
    cmd = [sys.executable, "-m", "vulture", "--min-confidence", "80", *config.roots]
    try:
        result = subprocess.run(  # nosec B603
            cmd,
            cwd=str(config.project_root),
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return []
    findings: list[Finding] = []
    for line in result.stdout.splitlines():
        if not line.strip() or "unused" not in line:
            continue
        findings.append(
            Finding(
                category="unused_export",
                target=line.split(":", 1)[0],
                severity="low",
                detail={"vulture": line.strip()},
            )
        )
    return findings


def _unused_dependencies(graph: nx.DiGraph, config: AuditConfig) -> list[Finding]:
    declared = _declared_dependencies(config.project_root)
    if not declared:
        return []
    used = _imported_top_levels(graph)
    findings: list[Finding] = []
    for dep_name in declared - used:
        if dep_name.startswith("pyarnes-"):
            # Workspace members are wired through the workspace, not via
            # import strings — skip false positives for them.
            continue
        findings.append(
            Finding(
                category="unused_dep",
                target=dep_name,
                severity="medium",
                detail={"declared_in": "pyproject.toml"},
            )
        )
    return findings


def _declared_dependencies(project_root: Path) -> set[str]:
    declared: set[str] = set()
    for pyproject in [project_root / "pyproject.toml", *project_root.glob("packages/*/pyproject.toml")]:
        if not pyproject.is_file():
            continue
        try:
            with pyproject.open("rb") as fh:
                data = tomllib.load(fh)
        except (OSError, tomllib.TOMLDecodeError):
            continue
        for raw in data.get("project", {}).get("dependencies", []):
            declared.add(_dep_name(raw))
    return declared


def _dep_name(raw: str) -> str:
    # `package>=1.0` → `package`; `package[extra]` → `package`.
    name = raw.split(";", 1)[0]
    for sep in ("==", ">=", "<=", "~=", ">", "<", "[", " "):
        if sep in name:
            name = name.split(sep, 1)[0]
    return name.strip().replace("_", "-").lower()


def _imported_top_levels(graph: nx.DiGraph) -> set[str]:
    imports: set[str] = set()
    for _src, dst, attrs in graph.edges(data=True):
        if attrs.get("kind") not in {"imports", "imports_from"}:
            continue
        top = str(dst).split(".", 1)[0].replace("_", "-").lower()
        imports.add(top)
    return imports


def _feature_flag_usage(graph: nx.DiGraph, config: AuditConfig) -> list[Finding]:
    pattern = re.compile(config.flag_pattern)
    counts: dict[str, list[str]] = defaultdict(list)
    files_seen: set[str] = set()
    for _node_id, attrs in graph.nodes(data=True):
        file_path = attrs.get("file_path", "")
        if not file_path or file_path in files_seen:
            continue
        files_seen.add(file_path)
        full_path = (config.project_root / file_path).resolve()
        if not full_path.is_file():
            continue
        try:
            text = full_path.read_text(encoding="utf-8")
        except OSError:
            continue
        for match in pattern.finditer(text):
            flag = match.group(1) if match.groups() else match.group(0)
            counts[flag].append(file_path)
    findings: list[Finding] = []
    for flag, files in counts.items():
        findings.append(
            Finding(
                category="feature_flag",
                target=flag,
                severity="low",
                detail={"hit_count": len(files), "files": _unique(files)},
            )
        )
    return findings


def _unique(items: Iterable[str]) -> list[str]:
    seen: list[str] = []
    seen_set: set[str] = set()
    for item in items:
        if item not in seen_set:
            seen.append(item)
            seen_set.add(item)
    return seen
