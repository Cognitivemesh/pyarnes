"""Tests for AgentContext."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyarnes_harness.context import AgentContext


class TestAgentContextDirect:
    def test_defaults_are_empty(self) -> None:
        ctx = AgentContext(project_name="myproject")
        assert ctx.conventions == ()
        assert ctx.architecture_rules == ()
        assert ctx.testing_requirements == ()
        assert ctx.approved_libraries == frozenset()
        assert ctx.forbidden_patterns == ()

    def test_to_system_prompt_only_project_when_empty(self) -> None:
        ctx = AgentContext(project_name="myproject")
        prompt = ctx.to_system_prompt()
        assert "# Project: myproject" in prompt
        assert "## Conventions" not in prompt

    def test_to_system_prompt_renders_non_empty_sections(self) -> None:
        ctx = AgentContext(
            project_name="myproject",
            conventions=("async-first",),
            approved_libraries=frozenset({"httpx"}),
        )
        prompt = ctx.to_system_prompt()
        assert "## Conventions" in prompt
        assert "- async-first" in prompt
        assert "## Approved Libraries" in prompt
        assert "- httpx" in prompt
        assert "## Architecture Rules" not in prompt

    def test_to_system_prompt_skips_empty_sections(self) -> None:
        ctx = AgentContext(
            project_name="myproject",
            architecture_rules=("no circular imports",),
        )
        prompt = ctx.to_system_prompt()
        assert "## Conventions" not in prompt
        assert "## Architecture Rules" in prompt

    def test_immutable(self) -> None:
        ctx = AgentContext(project_name="p")
        with pytest.raises(AttributeError):
            ctx.project_name = "other"  # type: ignore[misc]


class TestAgentContextFromYaml:
    def test_loads_all_fields(self, tmp_path: Path) -> None:
        yaml_content = """\
project_name: testproj
conventions:
  - async-first
  - type hints everywhere
architecture_rules:
  - no circular imports
testing_requirements:
  - 100% branch coverage
approved_libraries:
  - httpx
  - pydantic
forbidden_patterns:
  - eval()
"""
        config_file = tmp_path / ".agents.yml"
        config_file.write_text(yaml_content)
        ctx = AgentContext.from_yaml(config_file)
        assert ctx.project_name == "testproj"
        assert ctx.conventions == ("async-first", "type hints everywhere")
        assert ctx.architecture_rules == ("no circular imports",)
        assert ctx.testing_requirements == ("100% branch coverage",)
        assert ctx.approved_libraries == frozenset({"httpx", "pydantic"})
        assert ctx.forbidden_patterns == ("eval()",)

    def test_missing_keys_default_to_empty(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".agents.yml"
        config_file.write_text("project_name: minimal\n")
        ctx = AgentContext.from_yaml(config_file)
        assert ctx.project_name == "minimal"
        assert ctx.conventions == ()

    def test_empty_file_uses_stem_as_name(self, tmp_path: Path) -> None:
        config_file = tmp_path / "myapp.yml"
        config_file.write_text("")
        ctx = AgentContext.from_yaml(config_file)
        assert ctx.project_name == "myapp"

    def test_yaml_lists_coerced_to_tuples(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".agents.yml"
        config_file.write_text("project_name: p\nconventions:\n  - a\n  - b\n")
        ctx = AgentContext.from_yaml(config_file)
        assert isinstance(ctx.conventions, tuple)
        assert isinstance(ctx.approved_libraries, frozenset)
