"""Tests for the orchestrator and the detectors that don't shell out."""

from __future__ import annotations

import io
from pathlib import Path

import networkx as nx

from pyarnes_bench.audit import AuditConfig, audit_graph, build_graph, summarize
from pyarnes_bench.audit.audit import _circular_imports, _unused_files
from pyarnes_core.observe.logger import LogFormat, configure_logging, get_logger


def _logger():
    sink = io.StringIO()
    configure_logging(level="INFO", fmt=LogFormat.JSON, stream=sink)
    return get_logger("audit-test"), sink


def test_unused_files_flags_module_with_no_inbound_imports() -> None:
    g: nx.DiGraph = nx.DiGraph()
    g.add_node("a.py::pkg.a", kind="module", name="pkg.a", qualname="pkg.a", file_path="a.py")
    g.add_node("b.py::pkg.b", kind="module", name="pkg.b", qualname="pkg.b", file_path="b.py")
    # Resolved edge — points at the importee's node id (post link-pass shape).
    g.add_edge("a.py::pkg.a", "b.py::pkg.b", kind="imports", file_path="a.py", line=1)

    findings = _unused_files(g)
    targets = {f.target for f in findings}
    # pkg.a is unused (nobody imports it); pkg.b is imported.
    assert "a.py::pkg.a" in targets
    assert "b.py::pkg.b" not in targets


def test_circular_imports_detected_in_two_module_cycle() -> None:
    g: nx.DiGraph = nx.DiGraph()
    g.add_node("pkg.a", kind="module", name="pkg.a", qualname="pkg.a")
    g.add_node("pkg.b", kind="module", name="pkg.b", qualname="pkg.b")
    g.add_edge("pkg.a", "pkg.b", kind="imports")
    g.add_edge("pkg.b", "pkg.a", kind="imports")

    findings = _circular_imports(g)
    assert findings
    cycles = [f.detail.get("cycle") for f in findings]
    assert any({"pkg.a", "pkg.b"}.issubset(set(c)) for c in cycles if c)


def test_audit_graph_emits_finding_events(tmp_path: Path) -> None:
    # Build a synthetic project with a real circular import.
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "src" / "pkg" / "a.py").write_text("from pkg.b import x\n", encoding="utf-8")
    (tmp_path / "src" / "pkg" / "b.py").write_text("from pkg.a import y\nx = 1\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pyarnes-audit]\nroots = ["src"]\nexclude = []\n',
        encoding="utf-8",
    )

    cfg = AuditConfig.load(tmp_path)
    sink = io.StringIO()
    configure_logging(level="INFO", fmt=LogFormat.JSON, stream=sink)
    logger = get_logger("audit-orchestrator")
    graph = build_graph(config=cfg, logger=logger, session_id="s", trace_id="t", step=0)
    findings = audit_graph(
        graph,
        config=cfg,
        logger=logger,
        session_id="s",
        trace_id="t",
        step=1,
    )
    summary = summarize(findings)

    # At least the circular import (HIGH) must be reported.
    assert summary.has_high
    assert any(f.category == "circular_import" for f in findings)
    output = sink.getvalue()
    assert '"event": "audit.finding"' in output
