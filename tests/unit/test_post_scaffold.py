"""Tests for post_scaffold task."""

from __future__ import annotations

import pyarnes_tasks.post_scaffold as ps_module
from pyarnes_tasks.post_scaffold import main


class TestPostScaffold:
    def test_sync_failure_returns_nonzero(self, monkeypatch, tmp_path) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(ps_module, "_run", lambda cmd: 1 if "sync" in cmd else 0)
        assert main() != 0

    def test_check_failure_non_5_returns_nonzero(self, monkeypatch, tmp_path) -> None:
        monkeypatch.chdir(tmp_path)

        def _run(cmd):
            if "sync" in cmd:
                return 0
            return 2  # unexpected failure

        monkeypatch.setattr(ps_module, "_run", _run)
        assert main() != 0

    def test_check_exit_5_treated_as_ok(self, monkeypatch, tmp_path) -> None:
        monkeypatch.chdir(tmp_path)

        def _run(cmd):
            if "sync" in cmd:
                return 0
            return 5  # no tests found

        monkeypatch.setattr(ps_module, "_run", _run)
        assert main() == 0

    def test_appends_checklist_to_agents_md(self, monkeypatch, tmp_path) -> None:
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("# Agents\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(ps_module, "_run", lambda _cmd: 0)
        assert main() == 0
        content = agents_md.read_text(encoding="utf-8")
        assert "Post-scaffold checklist" in content
        assert "uv run tasks check" in content

    def test_no_agents_md_does_not_error(self, monkeypatch, tmp_path) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(ps_module, "_run", lambda _cmd: 0)
        assert main() == 0

    def test_success_returns_zero(self, monkeypatch, tmp_path) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(ps_module, "_run", lambda _cmd: 0)
        assert main() == 0
