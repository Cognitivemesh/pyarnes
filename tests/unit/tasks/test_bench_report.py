"""Tests for ``pyarnes_tasks.bench_report`` — JSONL to markdown table."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

from pyarnes_tasks import bench_report


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


class TestBenchReport:
    """``main()`` renders a markdown table of scenario / score / reason."""

    def test_renders_table_header_and_rows(self, capsys, tmp_path: Path) -> None:
        jsonl = tmp_path / "eval.jsonl"
        _write_jsonl(jsonl, [
            {"scenario": "greeting", "score": 1.0, "metadata": {"reason": "match"}},
            {"scenario": "farewell", "score": 0.0, "reason": "mismatch"},
        ])
        with patch.object(sys, "argv", ["bench_report", str(jsonl)]):
            code = bench_report.main()
        assert code == 0
        out = capsys.readouterr().out
        assert "| scenario | score | reason |" in out
        assert "| greeting | 1.0 | match |" in out
        assert "| farewell | 0.0 | mismatch |" in out

    def test_missing_path_arg_returns_1(self, capsys) -> None:
        with patch.object(sys, "argv", ["bench_report"]):
            code = bench_report.main()
        assert code == 1
        assert "usage" in capsys.readouterr().err

    def test_nonexistent_file_returns_1(self, capsys, tmp_path: Path) -> None:
        with patch.object(sys, "argv", ["bench_report", str(tmp_path / "no.jsonl")]):
            code = bench_report.main()
        assert code == 1
        assert "not a file" in capsys.readouterr().err
