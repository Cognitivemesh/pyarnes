"""Tests for ``pyarnes_tasks.bench_run`` — adopter suite dispatch."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from pyarnes_tasks import bench_run


@pytest.fixture
def fake_suite_module(tmp_path: Path) -> str:
    """Write a throwaway module exposing ``build_suite`` under a temp sys.path entry."""
    pkg_dir = tmp_path / "_fake_bench_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "suite.py").write_text(
        textwrap.dedent("""
        from pyarnes_bench import EvalResult, EvalSuite

        def build_suite() -> EvalSuite:
            suite = EvalSuite(name="smoke")
            suite.add(EvalResult(
                scenario="hello", expected="hi", actual="hi", score=1.0, passed=True,
            ))
            return suite
    """)
    )
    sys.path.insert(0, str(tmp_path))
    yield "_fake_bench_pkg.suite"
    sys.path.remove(str(tmp_path))
    for mod in [m for m in sys.modules if m.startswith("_fake_bench_pkg")]:
        del sys.modules[mod]


class TestBenchRun:
    """``main()`` imports the module and prints the suite summary as JSON."""

    def test_prints_summary_for_sync_build_suite(self, capsys, fake_suite_module: str) -> None:
        with patch.object(sys, "argv", ["bench_run", fake_suite_module]):
            code = bench_run.main()
        assert code == 0
        out = capsys.readouterr().out
        assert '"suite": "smoke"' in out
        assert '"total": 1' in out
        assert '"pass_rate": 1.0' in out

    def test_missing_module_arg_returns_1(self, capsys) -> None:
        with patch.object(sys, "argv", ["bench_run"]):
            code = bench_run.main()
        assert code == 1
        assert "usage" in capsys.readouterr().err

    def test_module_without_build_suite_returns_1(self, tmp_path: Path, capsys) -> None:
        pkg = tmp_path / "_no_build_suite"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        sys.path.insert(0, str(tmp_path))
        try:
            with patch.object(sys, "argv", ["bench_run", "_no_build_suite"]):
                code = bench_run.main()
        finally:
            sys.path.remove(str(tmp_path))
            del sys.modules["_no_build_suite"]
        assert code == 1
        assert "build_suite is not defined" in capsys.readouterr().err
