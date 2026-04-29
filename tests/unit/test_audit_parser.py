"""Tests for ``pyarnes_bench.audit.parser`` — Python tree-sitter extraction."""

from __future__ import annotations

from pathlib import Path

from pyarnes_bench.audit.parser import PythonParser
from pyarnes_bench.audit.schema import EdgeKind, NodeKind


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_parser_extracts_class_function_and_call(tmp_path: Path) -> None:
    body = (
        "import os\n"
        "from pathlib import Path\n\n"
        "class A:\n"
        "    def m(self):\n"
        "        return os.getcwd()\n\n"
        "def f():\n"
        "    return Path('.')\n"
    )
    src = _write(tmp_path, "src/pkg/mod.py", body)
    parser = PythonParser()
    nodes, edges = parser.parse_file(src, project_root=tmp_path)

    kinds = [n.kind for n in nodes]
    assert NodeKind.MODULE in kinds
    assert NodeKind.CLASS in kinds
    assert NodeKind.METHOD in kinds  # A.m
    assert NodeKind.FUNCTION in kinds  # f

    edge_kinds = {e.kind for e in edges}
    assert EdgeKind.CONTAINS in edge_kinds
    assert EdgeKind.IMPORTS in edge_kinds
    assert EdgeKind.IMPORTS_FROM in edge_kinds
    assert EdgeKind.CALLS in edge_kinds


def test_parser_strips_src_layout_prefix_for_qualname(tmp_path: Path) -> None:
    src = _write(tmp_path, "packages/x/src/pkg/mod.py", "x = 1\n")
    parser = PythonParser()
    nodes, _ = parser.parse_file(src, project_root=tmp_path)
    module = next(n for n in nodes if n.kind == NodeKind.MODULE)
    # `packages/x/src/pkg/mod.py` -> qualname `pkg.mod`, not the full path.
    assert module.qualname == "pkg.mod"


def test_parser_handles_init_module(tmp_path: Path) -> None:
    src = _write(tmp_path, "src/pkg/__init__.py", "VERSION = '1'\n")
    parser = PythonParser()
    nodes, _ = parser.parse_file(src, project_root=tmp_path)
    module = next(n for n in nodes if n.kind == NodeKind.MODULE)
    assert module.qualname == "pkg"


def test_parser_records_inheritance(tmp_path: Path) -> None:
    src = _write(tmp_path, "src/pkg/m.py", "class Base: pass\nclass Sub(Base): pass\n")
    parser = PythonParser()
    _, edges = parser.parse_file(src, project_root=tmp_path)
    inherits = [e for e in edges if e.kind == EdgeKind.INHERITS]
    assert any(e.dst == "Base" for e in inherits)


def test_parser_emits_call_edges(tmp_path: Path) -> None:
    src = _write(tmp_path, "src/pkg/m.py", "def helper(): return 1\ndef f(): return helper()\n")
    parser = PythonParser()
    _, edges = parser.parse_file(src, project_root=tmp_path)
    calls = [e for e in edges if e.kind == EdgeKind.CALLS]
    assert any(e.dst == "helper" for e in calls)
