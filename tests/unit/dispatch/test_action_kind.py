"""Tests for dispatch.atoms.action_kind — B8 prep."""

from __future__ import annotations

from pyarnes_core.dispatch.atoms import ActionKind, classify


class TestClassify:
    """classify returns a three-valued verdict on model actions."""

    def test_final_answer(self) -> None:
        assert classify({"type": "final_answer", "content": "done"}) == ActionKind.FINAL_ANSWER

    def test_tool_call(self) -> None:
        action = {"type": "tool_call", "tool": "read_file", "arguments": {}}
        assert classify(action) == ActionKind.TOOL_CALL

    def test_tool_call_without_tool_name_is_unknown(self) -> None:
        # Empty tool name is a model error; the loop must feed it back as recoverable.
        assert classify({"type": "tool_call", "tool": ""}) == ActionKind.UNKNOWN

    def test_missing_type_is_unknown(self) -> None:
        assert classify({"content": "stray"}) == ActionKind.UNKNOWN

    def test_thinking_type_is_unknown(self) -> None:
        # B8 regression: "thinking" currently becomes a tool dispatch.
        assert classify({"type": "thinking"}) == ActionKind.UNKNOWN

    def test_chat_response_is_unknown(self) -> None:
        assert classify({"type": "chat_response", "content": "hi"}) == ActionKind.UNKNOWN
