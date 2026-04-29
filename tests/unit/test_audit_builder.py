"""Tests for ``pyarnes_bench.audit.builder``."""

from __future__ import annotations

import io
from pathlib import Path

from pyarnes_bench.audit import AuditConfig, build_graph
from pyarnes_core.observe.logger import LogFormat, configure_logging, get_logger


def _project(tmp_path: Path) -> AuditConfig:
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "src" / "pkg" / "a.py").write_text(
        "from pkg.b import helper\n\ndef call_helper():\n    return helper()\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "pkg" / "b.py").write_text(
        "def helper():\n    return 1\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pyarnes-audit]\nroots = ["src"]\nexclude = []\n',
        encoding="utf-8",
    )
    return AuditConfig.load(tmp_path)


def _logger():
    sink = io.StringIO()
    configure_logging(level="INFO", fmt=LogFormat.JSON, stream=sink)
    return get_logger("audit-builder-test"), sink


def test_build_graph_walks_roots(tmp_path: Path) -> None:
    cfg = _project(tmp_path)
    logger, _ = _logger()
    graph = build_graph(config=cfg, logger=logger, session_id="s", trace_id="t", step=0)
    # 3 modules (pkg, pkg.a, pkg.b) + 2 functions (call_helper, helper)
    assert graph.number_of_nodes() >= 5
    # CONTAINS + IMPORTS_FROM + CALLS edges all present.
    edge_kinds = {attrs["kind"] for _, _, attrs in graph.edges(data=True)}
    assert {"contains", "imports_from", "calls"}.issubset(edge_kinds)


def test_build_graph_emits_indexed_event(tmp_path: Path) -> None:
    cfg = _project(tmp_path)
    sink = io.StringIO()
    configure_logging(level="INFO", fmt=LogFormat.JSON, stream=sink)
    logger = get_logger("audit-builder-event")
    build_graph(config=cfg, logger=logger, session_id="s", trace_id="t", step=0)
    output = sink.getvalue()
    assert '"event": "audit.indexed"' in output
    assert '"session_id": "s"' in output
    assert '"trace_id": "t"' in output
