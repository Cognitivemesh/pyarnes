"""Typer CLI for the RTM/Toggl → unified agile reference adopter."""

from __future__ import annotations

import asyncio

import typer

from rtm_toggl_agile.pipeline import promote as pipeline_promote
from rtm_toggl_agile.schema import AgileWorkspace

app = typer.Typer(help="RTM + Toggl → unified agile workspace reference pipeline.")


@app.command(name="sync-rtm")
def sync_rtm() -> None:
    """Pull tasks from Remember-The-Milk. Stub — replace with a real client."""
    typer.echo("[stub] sync-rtm — replace ListRtmTasks.fixture with httpx calls")


@app.command(name="sync-toggl")
def sync_toggl() -> None:
    """Pull time entries from Toggl. Stub — replace with a real client."""
    typer.echo("[stub] sync-toggl — replace ListTogglEntries.fixture with httpx calls")


@app.command()
def promote() -> None:
    """Normalise both sources into the unified agile backend."""
    workspace = AgileWorkspace()
    asyncio.run(pipeline_promote(workspace))
    typer.echo(
        f"promoted {len(workspace.stories)} stories, {len(workspace.entries)} entries",
    )


if __name__ == "__main__":  # pragma: no cover
    app()
