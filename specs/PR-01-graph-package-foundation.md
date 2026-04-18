# PR-01 — Graph Package Foundation

## Context

First slice of the code-graph feature. Creates a new workspace member
`packages/graph/` containing **only** the storage layer: SQLModel schema, async
Turso/libsql engine, and a thin async repository. No extraction, no tools, no
analytics yet. This PR must land cleanly on `main` without touching any other
package's runtime code — downstream PRs build on the contracts defined here.

The parent plan selects **SQLModel + pydantic** as the ORM (matching the user's
other projects) and **Turso via `sqlalchemy-libsql`** as the storage backend so
that local-file and hosted-Turso are the same code path.

## Scope

**In**

- New package `packages/graph/` registered in the workspace.
- Three SQLModel tables: `GraphNode`, `GraphEdge`, `IndexMeta`.
- Async engine factory that creates schema idempotently on first use.
- Async repository (`upsert_nodes`, `upsert_edges`, `neighbors`, plus a
  `get_node` by id).
- Unit tests covering schema round-trip and repository helpers.
- `packages/graph/` picked up automatically by `[tool.pyarnes-tasks]` → `uv
  run tasks test`, `uv run tasks check` run green against it.

**Out (deferred to later PRs)**

- Tree-sitter extraction (PR-02).
- `graph:index` task (PR-02).
- Analytics / report (PR-03).
- Tools, MCP, hooks (PR-04).

## Files

### New

- `packages/graph/pyproject.toml` — workspace member metadata. Name:
  `pyarnes-graph`. Deps: `pyarnes-core`, `sqlmodel>=0.0.22`,
  `sqlalchemy[asyncio]>=2.0`, `sqlalchemy-libsql>=0.1`, `aiosqlite>=0.20`.
- `packages/graph/src/pyarnes_graph/__init__.py` — re-exports public surface
  (schema classes, `create_engine`).
- `packages/graph/src/pyarnes_graph/schema.py` — `NodeKind`, `EdgeKind`,
  `Confidence` enums + `GraphNode`, `GraphEdge`, `IndexMeta` SQLModel tables.
- `packages/graph/src/pyarnes_graph/store/__init__.py`
- `packages/graph/src/pyarnes_graph/store/engine.py` — `async def
  create_engine(db_path)` returning `AsyncEngine` with schema applied.
- `packages/graph/src/pyarnes_graph/store/repository.py` — async CRUD helpers.
- `tests/unit/graph/__init__.py`
- `tests/unit/graph/test_schema.py` — pydantic-validation + SQLModel table round-trip.
- `tests/unit/graph/test_repository.py` — upsert + neighbors query using an
  in-memory `sqlite+aiosqlite:///:memory:` engine.
- `tests/unit/graph/conftest.py` — `engine` and `session` async fixtures.

### Modified

- Root `pyproject.toml` — add `sqlmodel`, `sqlalchemy[asyncio]`,
  `sqlalchemy-libsql`, `aiosqlite` to the workspace-wide deps so mypy / ty can
  resolve them. `[tool.ruff].src` already uses glob `packages/*/src` — no edit
  needed.
- `uv.lock` — will regenerate on first `uv sync`.

## Reuse

| Existing utility | File | Used for |
|---|---|---|
| `get_logger(__name__)` | `packages/core/src/pyarnes_core/observe/logger.py` | Every module in the new package logs through the existing JSONL sink. Zero parallel logging. |
| `HarnessError` family | `packages/core/src/pyarnes_core/errors.py` | Storage failures raise `TransientError` (lock contention) / `UserFixableError` (missing libsql) / `UnexpectedError` (corrupt DB). No new error types. |
| `[tool.pyarnes-tasks]` auto-discovery | `packages/tasks/src/pyarnes_tasks/cli.py:42-56` | Zero task-runner changes needed — new package is picked up the moment the dir exists. |

## Design notes

1. **One module for the schema.** All three tables live in `schema.py` so the
   entire graph surface can be `grep`-read in ~120 lines.
2. **Enums as strings.** `NodeKind`, `EdgeKind`, `Confidence` inherit from
   `str, Enum` so `sqlite3 graph.db .dump` stays human-readable.
3. **`extra: dict` JSON escape hatch.** `GraphNode.extra` / `GraphEdge.extra`
   use `sa_column=Column(JSON)` so tree-sitter-specific metadata (AST node
   types, comment spans) can land without schema churn.
4. **Idempotent boot.** `create_engine` calls
   `SQLModel.metadata.create_all` inside an `engine.begin()` transaction. No
   Alembic at v1; re-index by deleting `.pyarnes/graph.db` until the first
   breaking schema change.
5. **Local vs remote Turso, same call signature.**
   `create_engine(Path("./.pyarnes/graph.db"))` → local file.
   `create_engine("sqlite+libsql://host?authToken=…")` → hosted Turso.
6. **Merge-based upsert.** `session.merge(node)` keeps insert-or-update in a
   single call — matches SQLModel idiom, no raw SQL.

## Acceptance

Run from the repo root:

```bash
uv sync                          # pulls sqlmodel / sqlalchemy-libsql / aiosqlite
uv run tasks test                # new tests/unit/graph/ passes (>= 6 tests)
uv run tasks check               # lint + typecheck + test, all green
uv run tasks lint                # ruff clean on packages/graph/
```

Smoke script (add to `tests/unit/graph/test_smoke.py`):

```python
import asyncio
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from pyarnes_graph.schema import GraphNode, NodeKind, Confidence
from pyarnes_graph.store.engine import create_engine
from pyarnes_graph.store.repository import upsert_nodes

async def test_smoke(tmp_path: Path) -> None:
    engine = await create_engine(tmp_path / "graph.db")
    async with AsyncSession(engine) as session:
        await upsert_nodes(session, [GraphNode(
            id="x::foo", kind=NodeKind.FUNCTION, name="foo",
            file_path="x.py", sha256="abc", confidence=Confidence.HIGH,
        )])
        await session.commit()
    assert (tmp_path / "graph.db").exists()
```

## Risks & rollback

- **Risk**: `sqlalchemy-libsql` doesn't install in CI on some Linux arch.
  **Mitigation**: `aiosqlite` is listed as a fallback dep; engine auto-detects
  URL scheme. CI can pin `sqlite+aiosqlite:///…` for now.
- **Rollback**: revert the PR — no other package imports `pyarnes_graph` yet,
  so there are no downstream breakages.

## Exit criteria (all must hold)

- [ ] `uv run tasks check` green on main.
- [ ] `pyarnes_graph` importable at the REPL: `from pyarnes_graph.schema import
  GraphNode` works.
- [ ] Schema round-trip test inserts + reads a `GraphNode` with an `extra` JSON
  payload.
- [ ] Coverage for the new package ≥ 50% (existing repo floor).
- [ ] Zero changes to `packages/core/`, `packages/harness/`, `packages/bench/`
  runtime code.
