"""Tests for analyse_code(deep=True) and ASTGuardrail."""

from __future__ import annotations

import pytest

import pyarnes_core.safety.semantic_judge as sj_module
from pyarnes_core.errors import LLMRecoverableError
from pyarnes_core.safety import analyse_code, scan_code_arguments
from pyarnes_core.safety.semantic_judge import DEEP_BANNED_CALLS, DEEP_BANNED_IMPORTS
from pyarnes_guardrails import ASTGuardrail

# ── Helpers ──────────────────────────────────────────────────────────────────


def _no_libcst(monkeypatch) -> None:
    """Make _analyse_code_deep act as if libcst is not installed."""
    monkeypatch.setattr(sj_module, "_analyse_code_deep", lambda *_, **__: [])


# ── Deep mode constants ───────────────────────────────────────────────────────


class TestDeepBannedSets:
    """Deep banned sets contain the expected entries."""

    def test_socket_in_deep_banned_imports(self) -> None:
        assert "socket" in DEEP_BANNED_IMPORTS

    def test_urllib_in_deep_banned_imports(self) -> None:
        assert "urllib" in DEEP_BANNED_IMPORTS

    def test_httpx_in_deep_banned_imports(self) -> None:
        assert "httpx" in DEEP_BANNED_IMPORTS

    def test_httpx_get_in_deep_banned_calls(self) -> None:
        assert "httpx.get" in DEEP_BANNED_CALLS

    def test_socket_socket_in_deep_banned_calls(self) -> None:
        assert "socket.socket" in DEEP_BANNED_CALLS


# ── analyse_code(deep=True) with libcst absent ────────────────────────────────


class TestAnalyseCodeDeepFallback:
    """When libcst is absent, deep=True gracefully falls back to ast analysis."""

    def test_still_catches_basic_banned_import(self, monkeypatch) -> None:
        _no_libcst(monkeypatch)
        findings = analyse_code("import subprocess", deep=True)
        assert any(f.symbol == "subprocess" for f in findings)

    def test_still_catches_banned_call(self, monkeypatch) -> None:
        _no_libcst(monkeypatch)
        findings = analyse_code("eval('x')", deep=True)
        assert any(f.kind == "call" and "eval" in f.symbol for f in findings)

    def test_empty_for_clean_code(self, monkeypatch) -> None:
        _no_libcst(monkeypatch)
        findings = analyse_code("x = 1 + 2", deep=True)
        assert findings == []


# ── analyse_code(deep=False) — deep analysis not added ───────────────────────


class TestAnalyseCodeShallowMode:
    """deep=False (default) does not run deep analysis."""

    def test_shallow_does_not_call_deep_analyser(self, monkeypatch) -> None:
        calls = []
        monkeypatch.setattr(sj_module, "_analyse_code_deep", lambda *a, **kw: calls.append(a) or [])
        analyse_code("import socket", deep=False)
        assert calls == []

    def test_deep_calls_deep_analyser(self, monkeypatch) -> None:
        calls = []
        monkeypatch.setattr(sj_module, "_analyse_code_deep", lambda *a, **kw: calls.append(a) or [])
        analyse_code("import socket", deep=True)
        assert len(calls) == 1


# ── scan_code_arguments with deep ────────────────────────────────────────────


class TestScanCodeArgumentsDeep:
    """scan_code_arguments passes deep flag through."""

    def test_deep_flag_forwarded(self, monkeypatch) -> None:
        received_deep: list[bool] = []

        original = sj_module.analyse_code

        def _spy(src: str, *, deep: bool = False, **kw: object) -> list:
            received_deep.append(deep)
            return original(src, deep=False, **kw)  # type: ignore[arg-type]

        monkeypatch.setattr(sj_module, "analyse_code", _spy)
        scan_code_arguments({"code": "x=1"}, keys=("code",), tool_name="t", deep=True)
        assert any(d is True for d in received_deep)


# ── ASTGuardrail ─────────────────────────────────────────────────────────────


class TestASTGuardrail:
    """ASTGuardrail delegates to scan_code_arguments."""

    def test_default_deep_is_true(self) -> None:
        g = ASTGuardrail()
        assert g.deep is True

    def test_default_code_keys(self) -> None:
        g = ASTGuardrail()
        assert "code" in g.code_keys
        assert "script" in g.code_keys
        assert "source" in g.code_keys

    def test_clean_code_passes(self) -> None:
        g = ASTGuardrail(deep=False)
        g.check("execute_code", {"code": "result = 2 + 2"})

    def test_eval_in_code_raises(self) -> None:
        g = ASTGuardrail(deep=False)
        with pytest.raises(LLMRecoverableError, match="eval"):
            g.check("execute_code", {"code": "eval('x')"})

    def test_subprocess_import_raises(self) -> None:
        g = ASTGuardrail(deep=False)
        with pytest.raises(LLMRecoverableError, match="subprocess"):
            g.check("execute_code", {"script": "import subprocess; subprocess.run(['ls'])"})

    def test_non_code_key_not_checked(self) -> None:
        g = ASTGuardrail(code_keys=("code",), deep=False)
        g.check("execute_code", {"command": "import subprocess"})

    def test_deep_mode_passes_flag(self, monkeypatch) -> None:
        received: list[bool] = []

        def _spy(args, *, keys, tool_name, deep=False, **kw):
            received.append(deep)

        monkeypatch.setattr(sj_module, "scan_code_arguments", _spy)
        import pyarnes_guardrails.guardrails as g_module  # noqa: PLC0415

        monkeypatch.setattr(g_module, "scan_code_arguments", _spy)
        g = ASTGuardrail(deep=True)
        g.check("execute_code", {"code": "x=1"})
        assert any(d is True for d in received)
