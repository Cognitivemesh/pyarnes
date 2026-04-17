"""Tool registry endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from pyarnes_api.schemas import ErrorResponse, ToolInfo, ToolListResponse
from pyarnes_harness.tools.registry import ToolRegistry

router = APIRouter(tags=["tools"])

# Shared registry instance.
_registry = ToolRegistry()


@router.get(
    "/tools",
    response_model=ToolListResponse,
    summary="List registered tools",
)
async def list_tools() -> ToolListResponse:
    """Return the names and handler types of all registered tools."""
    tools = [
        ToolInfo(name=name, handler_type=type(handler).__name__)
        for name, handler in _registry.as_dict().items()
    ]
    return ToolListResponse(tools=tools, count=len(tools))


@router.get(
    "/tools/{name}",
    response_model=ToolInfo,
    responses={404: {"model": ErrorResponse}},
    summary="Get a single tool",
)
async def get_tool(name: str) -> ToolInfo:
    """Return info about a specific registered tool."""
    handler = _registry.get(name)
    if handler is None:
        raise HTTPException(status_code=404, detail=f"Tool '{name}' not found")
    return ToolInfo(name=name, handler_type=type(handler).__name__)
