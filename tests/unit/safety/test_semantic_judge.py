"""Tests for safety.atoms.semantic_judge."""

from __future__ import annotations

import pytest

from pyarnes_core.errors import LLMRecoverableError
from pyarnes_core.safety import analyse_code, scan_code_arguments
from pyarnes_core.safety.semantic_judge import Finding


class TestAnalyseCode:
    """analyse_code returns findings for banned patterns."""

    def test_clean_code_has_no_findings(self) -> None:
        source = "x = 1 + 2\nprint(x)"
        assert analyse_code(source) == []

    def test_invalid_syntax_returns_empty(self) -> None:
        assert analyse_code("def (") == []

    def test_non_python_string_returns_empty(self) -> None:
        assert analyse_code("just a plain sentence") == []

    def test_banned_import_detected(self) -> None:
        source = "import subprocess"
        findings = analyse_code(source)
        assert len(findings) == 1
        assert findings[0] == Finding("import", "subprocess", 1, 0)

    def test_banned_import_from_detected(self) -> None:
        source = "from subprocess import run"
        findings = analyse_code(source)
        assert len(findings) == 1
        assert findings[0].kind == "import"
        assert findings[0].symbol == "subprocess"

    def test_ctypes_import_detected(self) -> None:
        findings = analyse_code("import ctypes")
        assert any(f.symbol == "ctypes" for f in findings)

    def test_importlib_detected(self) -> None:
        findings = analyse_code("import importlib")
        assert any(f.symbol == "importlib" for f in findings)

    def test_eval_call_detected(self) -> None:
        source = 'result = eval("1 + 1")'
        findings = analyse_code(source)
        assert len(findings) == 1
        assert findings[0] == Finding("call", "eval", 1, 9)

    def test_exec_call_detected(self) -> None:
        findings = analyse_code('exec("x = 1")')
        assert any(f.symbol == "exec" for f in findings)

    def test_compile_call_detected(self) -> None:
        findings = analyse_code('compile("x=1", "<s>", "exec")')
        assert any(f.symbol == "compile" for f in findings)

    def test_dunder_import_detected(self) -> None:
        findings = analyse_code('__import__("os")')
        assert any(f.symbol == "__import__" for f in findings)

    def test_os_system_call_detected(self) -> None:
        findings = analyse_code("import os\nos.system('ls')")
        assert any(f.symbol == "os.system" for f in findings)

    def test_os_popen_call_detected(self) -> None:
        findings = analyse_code("import os\nos.popen('cat /etc/passwd')")
        assert any(f.symbol == "os.popen" for f in findings)

    def test_multiple_findings_all_returned(self) -> None:
        source = "import subprocess\nimport ctypes"
        findings = analyse_code(source)
        assert len(findings) == 2

    def test_custom_banned_imports(self) -> None:
        source = "import pickle"
        findings = analyse_code(source, banned_imports=frozenset({"pickle"}))
        assert len(findings) == 1
        assert findings[0].symbol == "pickle"

    def test_custom_banned_calls(self) -> None:
        source = "open('/etc/passwd')"
        findings = analyse_code(source, banned_calls=frozenset({"open"}))
        assert len(findings) == 1
        assert findings[0].symbol == "open"


class TestScanCodeArguments:
    """scan_code_arguments raises LLMRecoverableError on first finding."""

    def test_clean_code_passes(self) -> None:
        scan_code_arguments({"code": "x = 1"}, keys=("code",), tool_name="run")

    def test_raises_on_eval(self) -> None:
        with pytest.raises(LLMRecoverableError, match="eval"):
            scan_code_arguments(
                {"code": 'eval("danger")'},
                keys=("code",),
                tool_name="execute",
            )

    def test_raises_on_banned_import(self) -> None:
        with pytest.raises(LLMRecoverableError, match="subprocess"):
            scan_code_arguments(
                {"source": "import subprocess"},
                keys=("source",),
                tool_name="execute",
            )

    def test_nested_key_is_walked(self) -> None:
        args = {"opts": {"code": "import subprocess\nx = 1"}}
        with pytest.raises(LLMRecoverableError):
            scan_code_arguments(args, keys=("code",), tool_name="run")

    def test_non_code_key_ignored(self) -> None:
        args = {"other": "import subprocess"}
        scan_code_arguments(args, keys=("code",), tool_name="run")

    def test_error_names_tool(self) -> None:
        with pytest.raises(LLMRecoverableError, match="my_tool"):
            scan_code_arguments(
                {"code": "exec('x')"},
                keys=("code",),
                tool_name="my_tool",
            )
