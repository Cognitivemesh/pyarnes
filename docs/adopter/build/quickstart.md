# Adopter quickstart

Scaffold a new project that consumes pyarnes packages via git URLs:

```bash
uvx copier copy gh:Cognitivemesh/pyarnes my-new-project
cd my-new-project
uv sync
uv run tasks check
```

The scaffolded project ships with a working entrypoint. The minimal end-to-end flow looks like this:

```python
import asyncio


async def main() -> None:
    """Run the agent's first iteration."""
    message = "hello from a freshly scaffolded pyarnes project"
    print(message)


if __name__ == "__main__":
    asyncio.run(main())
```

Add a tool to your scaffolded project under `src/<module>/tools/` and wire it into the harness loop. A simple tool looks like this:

```python
from typing import Any


def echo(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the payload unchanged — useful as a sanity tool during bring-up."""
    return {"echoed": payload}


def main() -> None:
    result = echo({"text": "ping"})
    print(result)


if __name__ == "__main__":
    main()
```

Run the project's task suite to validate the scaffold:

```bash
uv run tasks check
uv run tasks audit:check
```

These two commands gate every PR — `check` runs lint + typecheck + test, and `audit:check` exits non-zero on any HIGH finding from the in-tree code-graph audit.
