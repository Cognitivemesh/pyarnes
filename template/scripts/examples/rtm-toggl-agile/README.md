# rtm-toggl-agile examples

Standalone PEP 723 scripts demonstrating HTTP calls to task/time-tracking
APIs. No pyarnes dependency; no project-wide install.

## fetch-entries.py

Fetch recent Toggl time entries using
[httpx](https://pypi.org/project/httpx/) and validate them as
[pydantic](https://pypi.org/project/pydantic/) models.

```bash
TOGGL_API_TOKEN=your-token uv run scripts/examples/rtm-toggl-agile/fetch-entries.py
```

Grab a token from <https://track.toggl.com/profile>. First run downloads
`httpx` and `pydantic` into an isolated cached env.

## Lifting this into your project

When you're ready to integrate these services:

1. Add `httpx>=0.27` and `pydantic>=2.9` to `[project.dependencies]` in
   `pyproject.toml`.
2. Move the client calls into `src/{{ project_module }}/` or into
   `ToolHandler` subclasses under `.claude/agent_kit/tools/`.
