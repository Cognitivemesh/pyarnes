"""Tests for tool registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from pyarnes_core.types import ToolHandler
from pyarnes_harness.tools.registry import ToolRegistry


@dataclass
class StubTool(ToolHandler):
    """Satisfies the ToolHandler ABC."""

    async def execute(self, arguments: dict[str, Any]) -> Any:
        return "ok"


class TestToolRegistry:
    """ToolRegistry manages named tool handlers."""

    def test_register_and_get(self) -> None:
        reg = ToolRegistry()
        tool = StubTool()
        reg.register("stub", tool)
        assert reg.get("stub") is tool
        assert "stub" in reg
        assert len(reg) == 1

    def test_duplicate_raises(self) -> None:
        reg = ToolRegistry()
        reg.register("a", StubTool())
        with pytest.raises(ValueError, match="already registered"):
            reg.register("a", StubTool())

    def test_get_missing_returns_none(self) -> None:
        reg = ToolRegistry()
        assert reg.get("nope") is None

    def test_unregister(self) -> None:
        reg = ToolRegistry()
        reg.register("a", StubTool())
        reg.unregister("a")
        assert "a" not in reg

    def test_unregister_missing_raises(self) -> None:
        reg = ToolRegistry()
        with pytest.raises(KeyError, match="not registered"):
            reg.unregister("ghost")

    def test_names_sorted(self) -> None:
        reg = ToolRegistry()
        reg.register("z", StubTool())
        reg.register("a", StubTool())
        assert reg.names == ["a", "z"]

    def test_as_dict(self) -> None:
        reg = ToolRegistry()
        reg.register("x", StubTool())
        d = reg.as_dict()
        assert "x" in d


class TestStructuralToolHandler:
    """C12: ToolHandler is a Protocol; plain classes satisfy it structurally."""

    def test_plain_class_registers(self) -> None:
        class PlainTool:
            async def execute(self, arguments: dict[str, Any]) -> Any:
                return arguments

        reg = ToolRegistry()
        reg.register("plain", PlainTool())
        assert reg.get("plain") is not None

    def test_missing_execute_rejected(self) -> None:
        class NotATool:
            pass

        reg = ToolRegistry()
        with pytest.raises(TypeError, match="does not satisfy ToolHandler"):
            reg.register("broken", NotATool())  # type: ignore[arg-type]
