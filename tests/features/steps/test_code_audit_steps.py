"""BDD step definitions for the code-audit feature."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from pytest_bdd import given, scenario, then, when

from pyarnes_bench.audit import AuditConfig, audit_graph, build_graph, load_graph
from pyarnes_bench.audit.findings import Finding
from pyarnes_core.observe.logger import LogFormat, configure_logging, get_logger

FEATURE = "../code_audit.feature"


# ── Scenarios ──────────────────────────────────────────────────────────────


@scenario(FEATURE, "Build a graph for a clean project")
def test_build_clean() -> None:
    pass


@scenario(FEATURE, "Detect a circular import")
def test_detect_circular() -> None:
    pass


@scenario(FEATURE, "Reload the graph without re-parsing source")
def test_reload_graph() -> None:
    pass


# ── Helpers ────────────────────────────────────────────────────────────────


def _logger():
    sink = io.StringIO()
    configure_logging(level="INFO", fmt=LogFormat.JSON, stream=sink)
    return get_logger("audit-bdd"), sink


def _project_with_modules(tmp_path: Path) -> AuditConfig:
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "src" / "pkg" / "a.py").write_text("def fa(): return 1\n", encoding="utf-8")
    (tmp_path / "src" / "pkg" / "b.py").write_text(
        "from pkg.a import fa\n\ndef fb(): return fa()\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pyarnes-audit]\nroots = ["src"]\nexclude = []\n',
        encoding="utf-8",
    )
    return AuditConfig.load(tmp_path)


def _project_with_cycle(tmp_path: Path) -> AuditConfig:
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "src" / "pkg" / "a.py").write_text("from pkg.b import fb\n", encoding="utf-8")
    (tmp_path / "src" / "pkg" / "b.py").write_text(
        "from pkg.a import fa\n\ndef fb(): return 1\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pyarnes-audit]\nroots = ["src"]\nexclude = []\n',
        encoding="utf-8",
    )
    return AuditConfig.load(tmp_path)


# ── Steps ──────────────────────────────────────────────────────────────────


@given("a synthetic Python project with two modules", target_fixture="project")
def _synthetic_two_modules(tmp_path: Path) -> dict[str, Any]:
    return {"config": _project_with_modules(tmp_path)}


@given("a synthetic Python project with a circular import", target_fixture="project")
def _synthetic_cycle(tmp_path: Path) -> dict[str, Any]:
    return {"config": _project_with_cycle(tmp_path)}


@given("the audit graph has been built")
def _graph_already_built(project: dict[str, Any]) -> None:
    from pyarnes_bench.audit import save_graph

    cfg: AuditConfig = project["config"]
    logger, _ = _logger()
    graph = build_graph(config=cfg, logger=logger, session_id="s", trace_id="t", step=0)
    save_graph(graph, cfg.graph_path)
    project["graph"] = graph


@when("I build the audit graph")
def _build(project: dict[str, Any]) -> None:
    from pyarnes_bench.audit import save_graph

    cfg: AuditConfig = project["config"]
    logger, _ = _logger()
    graph = build_graph(config=cfg, logger=logger, session_id="s", trace_id="t", step=0)
    save_graph(graph, cfg.graph_path)
    project["graph"] = graph


@when("I run audit_graph against it")
def _run_audit(project: dict[str, Any]) -> None:
    cfg: AuditConfig = project["config"]
    logger, _ = _logger()
    project["findings"] = audit_graph(
        project["graph"],
        config=cfg,
        logger=logger,
        session_id="s",
        trace_id="t",
        step=1,
    )


@when("I reload the graph from disk")
def _reload(project: dict[str, Any]) -> None:
    cfg: AuditConfig = project["config"]
    project["loaded"] = load_graph(cfg.graph_path)


@then("the graph contains the modules")
def _has_modules(project: dict[str, Any]) -> None:
    graph = project["graph"]
    qualnames = {attrs.get("qualname") for _, attrs in graph.nodes(data=True) if attrs.get("kind") == "module"}
    assert {"pkg", "pkg.a", "pkg.b"}.issubset(qualnames), qualnames


@then("the graph file is persisted to disk")
def _persisted(project: dict[str, Any]) -> None:
    cfg: AuditConfig = project["config"]
    assert cfg.graph_path.is_file()


@then("a high-severity circular_import finding is reported")
def _high_circular(project: dict[str, Any]) -> None:
    findings: list[Finding] = project["findings"]
    assert any(f.category == "circular_import" and f.severity == "high" for f in findings)


@then("the loaded graph has the same node count as the built graph")
def _same_node_count(project: dict[str, Any]) -> None:
    assert project["loaded"].number_of_nodes() == project["graph"].number_of_nodes()
