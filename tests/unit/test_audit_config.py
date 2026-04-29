"""Tests for ``pyarnes_bench.audit.config``."""

from __future__ import annotations

from pathlib import Path

from pyarnes_bench.audit.config import AuditConfig


def test_load_returns_defaults_when_table_missing(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
    cfg = AuditConfig.load(tmp_path)
    assert cfg.roots == ["src"]
    assert cfg.duplicate_min_tokens == 40
    assert cfg.forbidden_edges == []
    assert cfg.graph_path.name == "graph.json"


def test_load_parses_full_table(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pyarnes-audit]\n"
        'graph_path = "build/audit/g.json"\n'
        'roots = ["src", "lib"]\n'
        'exclude = [".cache"]\n'
        'forbidden_edges = [["core", "harness"]]\n'
        'flag_pattern = "FLAG\\\\((\\\\w+)\\\\)"\n'
        "duplicate_min_tokens = 80\n",
        encoding="utf-8",
    )
    cfg = AuditConfig.load(tmp_path)
    assert cfg.roots == ["src", "lib"]
    assert cfg.exclude == [".cache"]
    assert cfg.forbidden_edges == [("core", "harness")]
    assert cfg.duplicate_min_tokens == 80
    assert cfg.graph_path.name == "g.json"


def test_load_tolerates_missing_pyproject(tmp_path: Path) -> None:
    cfg = AuditConfig.load(tmp_path)
    assert cfg.roots == ["src"]
