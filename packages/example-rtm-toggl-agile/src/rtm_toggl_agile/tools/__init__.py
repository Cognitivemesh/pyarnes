"""Tool handlers for the RTM/Toggl → agile-backend pipeline."""

from __future__ import annotations

from pyarnes_core.types import ToolHandler
from pyarnes_harness import ToolRegistry
from rtm_toggl_agile.schema import AgileWorkspace, Story, TimeEntry


class ListRtmTasks(ToolHandler):
    """Return the list of RTM tasks for ``arguments['list_id']``.

    The real adopter posts to ``https://api.rememberthemilk.com/services/rest/``
    via ``httpx.AsyncClient``. This stub returns a fixed fixture so tests
    can assert normalisation end-to-end without network.
    """

    def __init__(self, fixture: list[dict] | None = None) -> None:
        self.fixture = fixture or []

    async def execute(self, arguments: dict) -> list[dict]:
        _ = arguments.get("list_id")
        return list(self.fixture)


class ListTogglEntries(ToolHandler):
    """Return the list of Toggl time entries for ``arguments['workspace_id']``."""

    def __init__(self, fixture: list[dict] | None = None) -> None:
        self.fixture = fixture or []

    async def execute(self, arguments: dict) -> list[dict]:
        _ = arguments.get("workspace_id")
        return list(self.fixture)


class UpsertStory(ToolHandler):
    """Insert or update a story in the ``AgileWorkspace``."""

    def __init__(self, workspace: AgileWorkspace) -> None:
        self.workspace = workspace

    async def execute(self, arguments: dict) -> str:
        story = Story(
            story_id=arguments["story_id"],
            title=arguments["title"],
            tags=tuple(arguments.get("tags", ())),
            due_date=arguments.get("due_date"),
        )
        self.workspace.upsert_story(story)
        return story.story_id


class AddTimeEntry(ToolHandler):
    """Attach a Toggl time entry to a previously-upserted story."""

    def __init__(self, workspace: AgileWorkspace) -> None:
        self.workspace = workspace

    async def execute(self, arguments: dict) -> str:
        entry = TimeEntry(
            story_id=arguments["story_id"],
            seconds=int(arguments["seconds"]),
            tags=tuple(arguments.get("tags", ())),
        )
        self.workspace.add_time(entry)
        return entry.story_id


def register_tools(
    registry: ToolRegistry,
    *,
    workspace: AgileWorkspace,
    rtm_fixture: list[dict] | None = None,
    toggl_fixture: list[dict] | None = None,
) -> None:
    """Register every RTM/Toggl/agile tool on ``registry``."""
    registry.register("list_rtm_tasks", ListRtmTasks(rtm_fixture))
    registry.register("list_toggl_entries", ListTogglEntries(toggl_fixture))
    registry.register("upsert_story", UpsertStory(workspace))
    registry.register("add_time_entry", AddTimeEntry(workspace))
