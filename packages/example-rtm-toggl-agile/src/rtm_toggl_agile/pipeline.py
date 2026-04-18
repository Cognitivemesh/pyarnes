"""Orchestrate the RTM/Toggl → agile-backend pipeline."""

from __future__ import annotations

from typing import Any, cast

from pyarnes_core.observe.logger import get_logger
from pyarnes_guardrails import GuardrailChain, ToolAllowlistGuardrail
from pyarnes_harness import ToolRegistry
from rtm_toggl_agile.guardrails import ApiQuotaGuardrail, SecretScanGuardrail
from rtm_toggl_agile.schema import AgileWorkspace
from rtm_toggl_agile.tools import register_tools

log = get_logger(__name__)


def build_registry(
    workspace: AgileWorkspace,
    *,
    rtm_fixture: list[dict] | None = None,
    toggl_fixture: list[dict] | None = None,
) -> ToolRegistry:
    """Return a ``ToolRegistry`` populated with every pipeline tool."""
    registry = ToolRegistry()
    register_tools(
        registry,
        workspace=workspace,
        rtm_fixture=rtm_fixture,
        toggl_fixture=toggl_fixture,
    )
    return registry


def build_chain(tool_names: frozenset[str]) -> GuardrailChain:
    """Return the guardrail chain the pipeline invokes before every tool call."""
    return GuardrailChain(guardrails=[
        ToolAllowlistGuardrail(allowed_tools=tool_names),
        ApiQuotaGuardrail(calls_per_minute=60),
        SecretScanGuardrail(),
    ])


async def promote(
    workspace: AgileWorkspace,
    *,
    rtm_fixture: list[dict] | None = None,
    toggl_fixture: list[dict] | None = None,
) -> AgileWorkspace:
    """Run the full sync: RTM → stories, Toggl → time entries, merged into ``workspace``."""
    registry = build_registry(
        workspace, rtm_fixture=rtm_fixture, toggl_fixture=toggl_fixture,
    )
    tools = registry.as_dict()
    chain = build_chain(frozenset(registry.names))

    async def invoke(name: str, args: dict) -> Any:
        chain.check(name, args)
        return await tools[name].execute(args)

    rtm_tasks = cast("list[dict]", await invoke("list_rtm_tasks", {"list_id": "inbox"}))
    for task in rtm_tasks:
        await invoke("upsert_story", {
            "story_id": task["id"],
            "title": task["name"],
            "tags": task.get("tags", []),
            "due_date": task.get("due"),
        })

    toggl_entries = cast(
        "list[dict]",
        await invoke("list_toggl_entries", {"workspace_id": "default"}),
    )
    for entry in toggl_entries:
        await invoke("add_time_entry", {
            "story_id": entry["story_id"],
            "seconds": entry["duration"],
            "tags": entry.get("tags", []),
        })

    log.info(
        "pipeline.promote stories={stories} entries={entries}",
        stories=len(workspace.stories),
        entries=len(workspace.entries),
    )
    return workspace
