# pyarnes_swarm — Run Logger and Evaluation Capture

> **Spec header**
>
> | Field | Value |
> |---|---|
> | **Title** | pyarnes_swarm — Run Logger and Capture |
> | **Status** | active |
> | **Type** | evaluation-capture |
> | **Owns** | RunReport schema, EvalRunLogger, RunSink, TursoSink, .pyarnes/runs/<run_id>/ JSONL layout, ToolCallEntry serialization, dual-source ToolCallEntry normalization |
> | **Depends on** | 07-bench-integrated-axes.md, 06-hook-integration.md |
> | **Extends** | 12-token-budget.md |
> | **Supersedes** | harness-run-logger.md |
> | **Read after** | 07-bench-integrated-axes.md |
> | **Read before** | 23-graph-package.md |
> | **Not owned here** | evaluation semantics — `ScoreResult` and `EvalResult` schemas (see `07-bench-integrated-axes.md`); external hook contract (see `06-hook-integration.md`); token counting (see `12-token-budget.md`) |
> | **Last reviewed** | 2026-04-29 |

## Design Rationale

**Why a dedicated run-level capture spec instead of burying this in bench or hooks?** `ToolCallLogger` captures one tool call at a time. `EvalSuite` holds results in memory. Neither defines the persistent run-level contract that ties traces, summary metrics, and evaluation rows together. A separate spec makes the storage boundary explicit so bench workflows, hook integrations, and adopter dashboards all read the same shape.

**Why JSONL first and Turso second?** File append is the most robust default: it works offline, in CI, and with zero extra services. Turso is valuable for queryable history, but it is optional infrastructure. The canonical contract is "runs are always persisted locally; query backends are opt-in sinks."

**Why separate run metadata from adopter-generated reports?** `pyarnes_swarm` knows how a run behaved. It does not know what final markdown, HTML, or product artifact an adopter wants to publish. The library owns machine-readable run data; adopters own presentation artefacts.

## The problem

`ToolCallLogger` already writes JSONL traces, and `EvalSuite` already computes `EvalResult` rows, but there is no canonical persistent format that groups them into one run. `07-bench-integrated-axes.md` depends on:

- `RunReport` for wallclock/tokens/retries
- `EvalRunLogger` for writing evaluation rows
- `TursoSink` for queryable history

Without a dedicated contract, those examples refer to types that have no canonical home.

## Core types

### `RunReport`

Defined in `pyarnes_swarm.capture` as the run-level summary emitted once per completed agent run.

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
    cost: Cost | None = None
```

`wallclock_s` is the elapsed runtime for the whole run. `tokens_in` and `tokens_out` are aggregate usage numbers for the run, not per-scorer usage. Optional `cost` lets adopters persist monetary totals when a `CostCalculator` is wired in.

`Cost` and `TokenUsage` are imported from `pyarnes_swarm.bench.burn.types` (same source as `EvalResult` in `07-bench-integrated-axes.md`).

### `EvalResult` additive metadata

The base `EvalResult` schema is defined in `07-bench-integrated-axes.md`. This spec extends it with three optional fields so rows can be tied back to a run. This definition supersedes the baseline; spec 07 describes the pre-logger schema.

`EvalSuite.run()` continues to return `EvalResult`; the three new fields default to `None` and do not break existing callers:

```python
@dataclass(frozen=True)
class EvalResult:
    scenario: str
    expected: Any
    actual: Any
    score: float
    passed: bool
    usage: TokenUsage | None = None
    cost: Cost | None = None
    run_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
```

`Cost` and `TokenUsage` are imported from `pyarnes_swarm.bench.burn.types`.

These fields are additive and default to `None`, so they do not change the meaning of in-memory-only evaluation.

## `EvalRunLogger`

`EvalRunLogger` is the canonical writer for run-level evaluation artifacts.

```python
class EvalRunLogger:
    def __init__(
        self,
        run_dir: Path,
        sinks: list[RunSink] | None = None,
    ) -> None: ...

    async def log_summary(self, suite: EvalSuite, report: RunReport) -> None:
        # 1. ensure run_dir exists
        # 2. write metadata.json from RunReport
        # 3. append one JSON row per EvalResult into evaluation.jsonl
        # 4. fan out to optional sinks
```

Behavior rules:

- Local files are always written first.
- Sink failures must not corrupt the local JSON files.
- A second call appends evaluation rows; it never truncates earlier data.
- `report.md` is never created by the logger; adopters generate that separately if they want one.

## `RunSink` and `TursoSink`

### `RunSink`

```python
class RunSink(Protocol):
    async def write(self, suite: EvalSuite, report: RunReport) -> None: ...
    async def close(self) -> None: ...
```

This keeps the fan-out contract small: the logger owns local persistence, sinks own optional side effects.

### `TursoSink`

`TursoSink` is the canonical optional query backend.

```python
class TursoSink:
    def __init__(self, url: str, auth_token: str | None = None) -> None: ...

    async def write(self, suite: EvalSuite, report: RunReport) -> None:
        # insert one run row + one row per EvalResult
```

Requirements:

- Uses the same async libSQL/Turso stack as the rest of `pyarnes_swarm`
- No stdlib `sqlite3`
- Writes one run row plus one row per `EvalResult`
- Safe to omit entirely; local JSON remains the baseline contract

## `.pyarnes/runs/<run_id>/` layout

`EvalRunLogger` owns the machine-readable run directory:

```text
.pyarnes/runs/<run_id>/
├── metadata.json        # serialized RunReport
├── evaluation.jsonl     # one line per EvalResult
├── tool_calls.jsonl     # ToolCallLogger output for the same run
└── report.md            # optional adopter-generated artifact, not written by pyarnes_swarm
```

Rules:

- `run_id` is generated by the caller; a timestamp-plus-random suffix is recommended
- `tool_calls.jsonl` stays the `ToolCallLogger` contract
- `metadata.json` and `evaluation.jsonl` are owned by `EvalRunLogger`
- `report.md` is explicitly outside the library's responsibility

## Relationship to hooks and bench

- `06-hook-integration.md` owns Claude Code hook behavior and the dev-time `.pyarnes/` files written by hooks.
- This spec owns per-run capture for runtime and evaluation flows.
- `07-bench-integrated-axes.md` may assume these types exist and use them in examples, but should not redefine them.

In other words:

- hooks describe how events are captured during interactive development
- run logging describes how complete runs are persisted for evaluation and audit
- bench describes how those persisted artifacts are scored

## Public API and stability

The following are intended public, path-stable symbols for the capture/eval persistence surface:

- `pyarnes_swarm.capture.RunReport`
- `pyarnes_swarm.capture.EvalRunLogger`
- `pyarnes_swarm.capture.ToolCallLogger`
- `pyarnes_swarm.capture.read_cc_session`
- `pyarnes_swarm.capture.resolve_cc_session_path`
- `pyarnes_swarm.capture.sinks.RunSink`
- `pyarnes_swarm.capture.sinks.TursoSink`

Private and allowed to drift:

- exact JSON field ordering in `evaluation.jsonl`
- SQL table names or internal helper names used by `TursoSink`
- any `_`-prefixed serializer or file-writing helpers

## Test requirements

- `test_agent.py` covers `ToolCallLogger`, `CapturedOutput`, and Claude Code session adapters
- `test_bench_eval.py` covers `EvalRunLogger` local-file persistence and additive `EvalResult` run metadata
- `test_bus.py` or a dedicated capture test covers `TursoSink` with an in-memory or test Turso target
- CI enforces zero `sqlite3` imports in the capture and bench persistence paths

## Cross-references

**Depends on:**

- `06-hook-integration.md` — Claude Code hook audit trail and dev-time `.pyarnes/` layout
- `07-bench-integrated-axes.md` — evaluation workflows that consume `RunReport` and `EvalRunLogger`

**Extends:**

- `12-token-budget.md` — token accounting inputs that populate `RunReport.tokens_in` and `tokens_out`

## Dual-Source `ToolCallEntry` Normalization

To uniformly power the evaluator dimensions, metrics tracking must strictly homogenize both realtime execution outputs and historical transcripts. We achieve this by statically translating both datasets into a single unvarying structure: `ToolCallEntry`.

* **AgentLoop JSONL Logs:** Inherently emitted at runtime natively in the Pyarnes core schema.
* **Claude Code Transcripts:** Read via an adapter function (`resolve_cc_session_path`) which actively parses external local MCP traces/transcripts, then normalizes their arbitrary states into `ToolCallEntry` shapes.

Enforcing this dual-source normalization ensures evaluators grade retrospective transcriptions with the exact same criteria as live `Scorer.verdict()` executions.

## Session branching (P3)

`ToolCallEntry` gains an optional `parent_id` field so that a run history can form a tree instead of a flat list. This is the storage hook that lets a branching agent (e.g. one that explores multiple alternative plans from a shared prefix) persist its decision tree.

```python
@dataclass(frozen=True, slots=True)
class ToolCallEntry:
    # ... existing fields (tool, arguments, result, is_error, duration_seconds,
    # started_at, finished_at, etc.) ...
    parent_id: str | None = None
```

Semantics:

- `parent_id is None` (the default) means "no branching" — the entry is a top-level event in a linear run. **Existing JSONL logs need no migration**; entries without `parent_id` deserialise to `None`.
- A non-`None` `parent_id` references the id of an earlier `ToolCallEntry`. One parent may have many children; this is what makes the structure a tree.
- The reference is one-directional: children point to their parent. Readers reconstruct the tree by grouping children under their `parent_id`.
- Adopters who never branch never need to populate this field. Tools that don't care continue to read entries as a flat sequence.

The field is intentionally additive and optional. No replay tooling, scorer, or sink is required to interpret it.
