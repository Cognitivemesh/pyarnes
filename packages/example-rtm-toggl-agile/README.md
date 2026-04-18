# example-rtm-toggl-agile

Reference implementation of **Adopter C** for pyarnes (see
[`specs/04-template-adopter-c-meta-use.md`](../../specs/04-template-adopter-c-meta-use.md)).

Shape: **unified agile backend**. Pull tasks/tags from Remember-The-Milk and
time entries from Toggl → normalise into a shared schema → push into a
unified agile backend (stories, sprints, WIP limits, time-tracked-to-story
links).

This adopter is the one the plan calls the **meta-use** case: pyarnes is
imported *twice* — once for the shipped product (this package) and a second
time as the Claude Code hook chain that harnesses the coding agent building
this package. The second import lives in the Copier template under
`.claude/hooks/` and ships only when `enable_dev_hooks=true`.

The HTTP clients for RTM and Toggl are replaced with dict-backed stubs so
tests stay fast; swap in `httpx.AsyncClient` for production.

## Commands

```bash
uv run rtm-toggl-agile sync-rtm
uv run rtm-toggl-agile sync-toggl
uv run rtm-toggl-agile promote
```
