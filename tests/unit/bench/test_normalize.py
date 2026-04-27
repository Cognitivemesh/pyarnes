"""Tests for tool-name and model-alias normalisation."""

from __future__ import annotations

from pyarnes_bench.burn.normalize import (
    MODEL_ALIASES,
    ModelAlias,
    normalize_tool,
    resolve_model,
)


class TestNormalizeTool:
    def test_canonical_aliases_collapse(self) -> None:
        assert normalize_tool("Bash") == "Bash"
        assert normalize_tool("bash") == "Bash"
        assert normalize_tool("BashTool") == "Bash"
        assert normalize_tool("exec_command") == "Bash"

    def test_edit_aliases(self) -> None:
        assert normalize_tool("str_replace_editor") == "Edit"
        assert normalize_tool("apply_patch") == "Edit"
        assert normalize_tool("MultiEdit") == "Edit"

    def test_mcp_collapses_to_label(self) -> None:
        assert normalize_tool("mcp__github__create_pr") == "MCP"
        assert normalize_tool("MCP__server__op") == "MCP"

    def test_unknown_tool_passes_through(self) -> None:
        assert normalize_tool("CustomTool") == "CustomTool"
        assert normalize_tool("") == ""


class TestResolveModel:
    def test_known_alias_resolves_to_canonical(self) -> None:
        assert resolve_model("my-proxy-opus") == "claude-opus-4-7"

    def test_unknown_returns_original(self) -> None:
        assert resolve_model("some-unknown-model") == "some-unknown-model"

    def test_explicit_alias_table_overrides_default(self) -> None:
        custom = {"prox-x": ModelAlias("prox-x", "real-y", "fam")}
        assert resolve_model("prox-x", custom) == "real-y"
        # default still works for built-ins
        assert resolve_model("my-proxy-opus", MODEL_ALIASES) == "claude-opus-4-7"

    def test_empty_string_unchanged(self) -> None:
        assert resolve_model("") == ""
