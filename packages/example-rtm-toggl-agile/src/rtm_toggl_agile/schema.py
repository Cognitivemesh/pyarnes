"""Shared schema the RTM and Toggl importers normalise into."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Story:
    """Unified representation of a story in the target agile backend."""

    story_id: str
    title: str
    tags: tuple[str, ...] = ()
    due_date: str | None = None


@dataclass(frozen=True, slots=True)
class TimeEntry:
    """Unified time-tracking record linked to a ``Story`` by ``story_id``."""

    story_id: str
    seconds: int
    tags: tuple[str, ...] = ()


@dataclass
class AgileWorkspace:
    """In-memory representation of the unified agile backend.

    Real adopters replace this with an HTTP/DB client; the interface is
    stable so the rest of the pipeline does not change.
    """

    stories: dict[str, Story] = field(default_factory=dict)
    entries: list[TimeEntry] = field(default_factory=list)

    def upsert_story(self, story: Story) -> None:
        self.stories[story.story_id] = story

    def add_time(self, entry: TimeEntry) -> None:
        self.entries.append(entry)
