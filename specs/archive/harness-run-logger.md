# harness-run-logger

**Status:** Implemented. Last refreshed 2026-04-22.

## Sources

Two trajectory sources land in the same `ToolCallEntry` shape, so
downstream bench scorers don't care which one produced a run:

| Source | Writer | Adapter |
|---|---|---|
| In-process `AgentLoop` | `pyarnes_harness.ToolCallLogger` (JSONL) | `ToolCallLogger` writes `ToolCallEntry` directly. |
| Claude Code session | Claude Code writes `~/.claude/projects/<escaped-cwd>/<session>.jsonl` (schema undocumented). | `pyarnes_harness.read_cc_session(path)` / `resolve_cc_session_path(cwd, session_id)` map the transcript into `ToolCallEntry` iterables, locked to the captured fixture at `tests/unit/fixtures/cc_session_sample.jsonl`. |

Contract for per-run persistence of evaluation artefacts in
`pyarnes-harness`, with an optional async **Turso** (libSQL) sink
alongside the default JSONL writer. Stdlib `sqlite3` is **forbidden**.

Closes **Themes 2 and 4** of the `packages/bench/` review (see
`/root/.claude/plans/could-please-review-and-drifting-dongarra.md`).

## Context

Today, `pyarnes-bench` is in-memory only: `EvalSuite` holds results
for the duration of a process and disappears. `pyarnes-harness` has
`ToolCallLogger` (file-only JSONL append) but nothing equivalent for
bench summaries or run-level metadata.

Agents-eval (qte77) solves this with a `RunContext` singleton that
routes every artefact into a single per-run directory (`metadata.json`,
`evaluation.json`, `trace.json`, `report.md`) and a separate
TraceCollector that writes to **SQLite**. We adopt the per-run-dir
idea but **swap SQLite for Turso** — `specs/PR-01-graph-package-
foundation.md` has already standardised on "async Turso engine +
repository" for this repo, so reusing that stack keeps the dependency
surface flat.

## Goals / non-goals

**Goals.**

- Add `EvalRunLogger` next to `ToolCallLogger` in
  `packages/harness/src/pyarnes_harness/capture/`.
- Establish the `.pyarnes/runs/<run_id>/` directory convention and
  document it in `docs/adopter/evaluate/logging.md`.
- Add optional `run_id / started_at / finished_at` fields to
  `EvalResult` (default `None` → no surface break).
- Add a `RunReport` frozen dataclass to `pyarnes_core.types`.
- Ship an **optional** `TursoSink` that can be passed to
  `EvalRunLogger` for queryable run history.

**Non-goals.**

- No new package — everything lives in existing
  `pyarnes-harness` and `pyarnes-core`.
- No stdlib `sqlite3` anywhere. libSQL/Turso via the async
  `libsql-client` + `SQLModel` stack already chosen by PR-01.
- No metrics server, no Prometheus endpoint, no OTel. Those remain
  adopter-owned.
- No GUI / dashboard / viewer.

## Proposed design

### `RunReport` (new, `pyarnes_core.types`)

```python
@dataclass(frozen=True, slots=True)
class RunReport:
    run_id: str
    started_at: datetime
    finished_at: datetime
    iterations: int
    retries: int
    wallclock_s: float
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
```

Produced by the harness loop on completion. Consumed by
`EvalRunLogger` (persistence) and by trajectory scorers defined in
`bench-use-cases-coding-and-deep-agents.md`.

### `EvalResult` — optional fields added

```python
# packages/bench/src/pyarnes_bench/result.py
run_id: str | None = None
started_at: datetime | None = None
finished_at: datetime | None = None
```

All default to `None`; the stable-surface golden test accepts
additive changes.

### `EvalRunLogger` (new, `pyarnes_harness.capture`)

```python
class EvalRunLogger:
    def __init__(
        self,
        run_dir: Path,
        sinks: list[RunSink] | None = None,
    ) -> None: ...

    async def log_summary(self, suite: EvalSuite, report: RunReport) -> None:
        # 1. JSONL append to <run_dir>/evaluation.jsonl
        # 2. For each sink in self.sinks: await sink.write(suite, report)
```

`RunSink` is a small `Protocol` (two methods: `write`, `close`).
JSONL-to-file is always on (matches `ToolCallLogger` pattern).
Extra sinks are opt-in.

### `TursoSink` (new, `pyarnes_harness.capture.sinks`)

```python
class TursoSink(RunSink):
    def __init__(self, url: str, auth_token: str | None = None) -> None:
        # use libsql-client async driver (same as graph PR-01)
        ...

    async def write(self, suite: EvalSuite, report: RunReport) -> None:
        # INSERT one row into eval_runs, one row per EvalResult into eval_results
        ...
```

Schema: two SQLModel tables (`EvalRunRow`, `EvalResultRow`) living in
`packages/harness/src/pyarnes_harness/capture/sinks/turso_schema.py`.
Never import `sqlite3` — only `libsql_client`.

### `.pyarnes/runs/<run_id>/` directory convention

Documented path only, created lazily by `EvalRunLogger.__init__`:

```
.pyarnes/runs/<run_id>/
├── metadata.json       # RunReport as JSON
├── evaluation.jsonl    # one line per EvalResult
├── tool_calls.jsonl    # existing ToolCallLogger output
└── report.md           # adopter-generated (not pyarnes' concern)
```

`run_id` = `datetime.utcnow().strftime("%Y%m%dT%H%M%SZ") + "-" + short_uuid`.

## Tests / acceptance

- `tests/unit/test_eval_run_logger.py`:
  - JSONL-only default: `log_summary` writes one line per result,
    creates `metadata.json` with the `RunReport`.
  - With `TursoSink(url=":memory:")`: row count in `eval_runs` ==
    1, row count in `eval_results` == `len(suite.results)`.
  - Re-entrant: second call appends, never overwrites.
  - Sink failure does not corrupt the JSONL (transaction-style
    ordering: JSONL first, sinks second).

- `tests/unit/test_stable_surface.py` — golden updated to include
  `RunReport`, `EvalRunLogger`, `RunSink`, `TursoSink`.

- `uv run tasks check` green.

- `rg -n "import sqlite3|from sqlite3" packages/harness/src` returns
  **zero** hits. A ruff custom rule (or a CI grep step) enforces
  this — see the Open questions section.

## Reuse

- `ToolCallLogger` in
  `packages/harness/src/pyarnes_harness/capture/tool_log.py` — copy
  its JSONL-append pattern verbatim; do not reinvent.
- `libsql-client` async driver + `SQLModel` setup from
  `specs/PR-01-graph-package-foundation.md` — reuse the engine
  factory helper rather than creating a second one.
- `returns.Result` from the `returns` library (listed in CLAUDE.md)
  for sink error paths — failing sinks return `Failure[_]` and the
  logger keeps going.

## Risks & rollback

- **Risk:** A slow Turso sink blocks the evaluation completion.
  **Mitigation:** sinks run under `asyncio.wait_for` with a
  5-second default timeout; on timeout the sink is skipped and a
  warning is logged.
- **Risk:** Disk-full on `.pyarnes/runs/`. **Mitigation:** JSONL
  write uses `fsync`-less append; on `OSError` the logger raises
  `UnexpectedError` so the caller can decide.
- **Rollback:** `EvalRunLogger` is opt-in (adopter constructs it).
  Simply remove the `sinks=[...]` argument and it degrades to JSONL
  only. Removing the feature altogether requires reverting the
  `EvalResult` optional fields — additive, so safe.

## Exit criteria

- All tests listed above green on `claude/review-bench-package-IbVai`.
- `CHANGELOG.md` "Added" section lists the new symbols.
- `docs/adopter/evaluate/logging.md` documents the `.pyarnes/runs/`
  layout.
- No `sqlite3` import anywhere in `packages/`.

## Open questions

- Do we enforce the "no `sqlite3`" rule via a ruff custom rule or
  via a CI grep step? **Lean:** ruff rule so it fires during `tasks
  lint`, not only in CI.
- Should `EvalRunLogger` also write a `report.md` by default?
  **Lean:** no — leave it to adopters; the `tasks bench:report`
  command proposed in Theme 7 already covers the generation path.
- Schema versioning for the Turso tables: hard-code `schema_version`
  column from day one, or add it later? **Lean:** day one — one
  migration is cheaper than a breaking reshape.
