# pyarnes

Minimal agentic harness engineering template that collaborates with Claude Code, Cursor, and Codex by adding verification loops, safety enforcement, and lifecycle management.

## Quick links

- [Adopter quickstart](adopter/build/quickstart.md) — scaffold a new project that depends on pyarnes packages.
- Project repository: [Cognitivemesh/pyarnes](https://github.com/Cognitivemesh/pyarnes).

## What's inside

- `pyarnes-core` — types, errors, lifecycle, observability primitives.
- `pyarnes-harness` — the agent loop, tools, capture.
- `pyarnes-guardrails` — composable safety guardrails.
- `pyarnes-bench` — evaluation and benchmarking toolkit (includes the `audit` subsystem).
- `pyarnes-tasks` — the `tasks` CLI used by every adopter project.

A typical adopter project's entrypoint is async-first:

```python
import asyncio


async def main() -> None:
    print("hello from pyarnes")


if __name__ == "__main__":
    asyncio.run(main())
```
