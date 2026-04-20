---
persona: adopter
level: L1
tags: [adopter, bootstrap, first-steps, onboarding]
---

# First steps after scaffolding

You have just run `uvx copier copy gh:Cognitivemesh/pyarnes my-agent` and
`uv sync` completed without errors. This page walks you through the first
things to change before writing any application logic.

## 1. Rename the placeholder module

The template creates `src/my_agent/` (derived from your project name). Open
`pyproject.toml` and confirm the package name matches what you answered during
scaffolding:

```toml
[project]
name = "my-agent"

[tool.setuptools.packages.find]
where = ["src"]
```

If you need to rename the Python package (not just the project), update both
`pyproject.toml` and the directory under `src/`.

## 2. Run the quality gate

```bash
uv run tasks check
```

This runs lint + typecheck + tests. On a fresh scaffold it should pass with zero
findings. If it fails, check the output of each sub-task:

```bash
uv run tasks lint        # ruff lint
uv run tasks typecheck   # ty type checking
uv run tasks test        # pytest
```

## 3. Write your first tool

Create `src/my_agent/tools.py`:

```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyarnes_core.types import ToolHandler


@dataclass
class ReadFileTool(ToolHandler):
    """Read a file from the workspace."""

    async def execute(self, arguments: dict[str, Any]) -> Any:
        path = arguments["path"]
        return await asyncio.to_thread(Path(path).read_text)
```

Then write a test before implementing more logic (`uv run tasks watch` keeps
pytest running on every save):

```bash
uv run tasks watch
```

See [Quick start](../build/quickstart.md) for the full tool + loop + guardrail
wiring.

## 4. Add guardrails

Every tool that touches the filesystem needs a `PathGuardrail`:

```python
from pyarnes_guardrails import GuardrailChain, PathGuardrail

chain = GuardrailChain(guardrails=[
    PathGuardrail(allowed_roots=("/workspace",)),
])
```

See [Security & threat model](../evaluate/security.md) for the full guardrail
list and when to use each one.

## 5. Configure logging

In your entry point, call `configure_logging` before anything else:

```python
from pyarnes_core.observe.logger import configure_logging

configure_logging(level="DEBUG", json=False)   # human-readable during dev
# configure_logging(level="INFO", json=True)   # JSONL for production
```

## 6. Pull template updates

As pyarnes ships improvements, pull them into your project:

```bash
uv run tasks update      # wraps `copier update`
```

This re-runs the Copier template diff and surfaces conflicts as merge markers
so you can choose which changes to keep.

## See also

- [Scaffold a project](scaffold.md) — full scaffolding reference.
- [Install & verify](install.md) — troubleshoot `uv sync` failures.
- [Quick start](../build/quickstart.md) — tool + loop + guardrail wiring.
- [FAQ & troubleshooting](../evaluate/faq.md) — common stumbles.
