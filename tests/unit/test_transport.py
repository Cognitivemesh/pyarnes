"""Tests for the provider transport abstraction layer."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pyarnes_core.errors import LLMRecoverableError
from pyarnes_harness.tools.registry import ToolRegistry, ToolSchema
from pyarnes_harness.transport.ports import (
    NormalizedResponse,
    NormalizedToolCall,
    TransportModelClient,
)

# ── ToolSchema ─────────────────────────────────────────────────────────────


def test_tool_schema_fields() -> None:
    schema = ToolSchema(
        name="read_file",
        description="Read a file from disk",
        parameters={"type": "object", "properties": {"path": {"type": "string"}}},
    )
    assert schema.name == "read_file"
    assert schema.description == "Read a file from disk"
    assert "path" in schema.parameters["properties"]


def test_tool_registry_register_schema() -> None:
    registry = ToolRegistry()
    schema = ToolSchema(name="my_tool", description="does stuff", parameters={})
    registry.register_schema("my_tool", schema)
    assert len(registry.schemas()) == 1
    assert registry.schemas()[0].name == "my_tool"


def test_tool_registry_schemas_empty_by_default() -> None:
    assert ToolRegistry().schemas() == []


def test_tool_registry_register_schema_duplicate_raises() -> None:
    registry = ToolRegistry()
    schema = ToolSchema(name="t", description="d", parameters={})
    registry.register_schema("t", schema)
    with pytest.raises(ValueError, match="already"):
        registry.register_schema("t", schema)


# ── NormalizedResponse / NormalizedToolCall ────────────────────────────────


def test_normalized_tool_call_fields() -> None:
    tc = NormalizedToolCall(id="tc1", name="fn", arguments='{"x": 1}')
    assert tc.id == "tc1"
    assert tc.name == "fn"
    assert tc.arguments == '{"x": 1}'


def test_normalized_response_stop() -> None:
    resp = NormalizedResponse(content="done", tool_calls=[], finish_reason="stop")
    assert resp.finish_reason == "stop"
    assert resp.tool_calls == []


def test_normalized_response_with_usage() -> None:
    resp = NormalizedResponse(
        content="", tool_calls=[], finish_reason="stop", usage={"input": 10, "output": 5}
    )
    assert resp.usage == {"input": 10, "output": 5}


# ── TransportModelClient ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_transport_client_final_answer() -> None:
    """NormalizedResponse with finish_reason='stop' → final_answer action."""
    transport = MagicMock()
    transport.complete = AsyncMock(
        return_value=NormalizedResponse(
            content="The answer is 42.",
            tool_calls=[],
            finish_reason="stop",
        )
    )
    client = TransportModelClient(transport=transport, registry=ToolRegistry())
    action = await client.next_action([{"role": "user", "content": "hi"}])
    assert action["type"] == "final_answer"
    assert action["content"] == "The answer is 42."


@pytest.mark.asyncio
async def test_transport_client_single_tool_call() -> None:
    """Single tool_call → well-formed action dict."""
    transport = MagicMock()
    transport.complete = AsyncMock(
        return_value=NormalizedResponse(
            content="",
            tool_calls=[NormalizedToolCall(id="tc1", name="search", arguments='{"q": "foo"}')],
            finish_reason="tool_calls",
        )
    )
    client = TransportModelClient(transport=transport, registry=ToolRegistry())
    action = await client.next_action([])
    assert action["type"] == "tool_call"
    assert action["tool"] == "search"
    assert action["id"] == "tc1"
    assert action["arguments"] == {"q": "foo"}


@pytest.mark.asyncio
async def test_transport_client_multi_tool_calls_raises() -> None:
    """Multiple tool calls in one response → LLMRecoverableError (Phase 4 guard)."""
    transport = MagicMock()
    transport.complete = AsyncMock(
        return_value=NormalizedResponse(
            content="",
            tool_calls=[
                NormalizedToolCall(id="tc1", name="a", arguments="{}"),
                NormalizedToolCall(id="tc2", name="b", arguments="{}"),
            ],
            finish_reason="tool_calls",
        )
    )
    client = TransportModelClient(transport=transport, registry=ToolRegistry())
    with pytest.raises(LLMRecoverableError, match="multiple"):
        await client.next_action([])


@pytest.mark.asyncio
async def test_transport_client_repairs_malformed_arguments() -> None:
    """Trailing-comma JSON in tool arguments is repaired transparently."""
    transport = MagicMock()
    transport.complete = AsyncMock(
        return_value=NormalizedResponse(
            content="",
            tool_calls=[NormalizedToolCall(id="t1", name="fn", arguments='{"x": 1,}')],
            finish_reason="tool_calls",
        )
    )
    client = TransportModelClient(transport=transport, registry=ToolRegistry())
    action = await client.next_action([])
    assert action["arguments"] == {"x": 1}


@pytest.mark.asyncio
async def test_transport_client_passes_tools_to_transport() -> None:
    """Registered schemas are forwarded as tool defs to transport.complete()."""
    transport = MagicMock()
    transport.complete = AsyncMock(
        return_value=NormalizedResponse(content="ok", tool_calls=[], finish_reason="stop")
    )
    registry = ToolRegistry()
    registry.register_schema(
        "my_tool",
        ToolSchema(name="my_tool", description="d", parameters={"type": "object"}),
    )
    client = TransportModelClient(transport=transport, registry=registry)
    await client.next_action([{"role": "user", "content": "hi"}])

    call_kwargs = transport.complete.call_args
    tools_arg = call_kwargs[1].get("tools") or call_kwargs[0][1]
    assert len(tools_arg) == 1
    assert tools_arg[0]["name"] == "my_tool"
