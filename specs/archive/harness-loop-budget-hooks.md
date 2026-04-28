# harness-loop-budget-hooks

**Status:** Implemented (library primitives + Claude Code hook wiring).
Last refreshed 2026-04-22.

- `Budget` lives at `pyarnes_core.budget:Budget` and is re-exported via
  `pyarnes_core.__init__`.
- `Lifecycle` grew `.budget` + `.dump(path)` + `.load(path)` so a
  Claude Code `SessionEnd` hook can snapshot state and `SessionStart`
  can restore it.
- The Claude Code `Stop` hook (`template/.claude/hooks/pyarnes_stop.py`)
  reads the checkpoint and emits
  `{"continue": false, "stopReason": …}` when a cap is hit — the only
  CC-documented mechanism for ending a session mid-flight.
- Token accounting is best-effort: current CC transcripts carry
  `message.usage.input_tokens` / `output_tokens` but the JSONL schema
  is not a public contract, so call-count and wall-time caps are the
  reliable enforcement path.

Contract for three opt-in `LoopConfig` hooks — `budget`, `guardrails`,
`lifecycle` — plus a `LoopBudget` type in `pyarnes_core.types` and the
async-scorer migration that these hooks enable.

Closes **Themes 4 and 5** of the `packages/bench/` review (see
`/root/.claude/plans/could-please-review-and-drifting-dongarra.md`).

## Context

The harness loop today runs until the model signals completion. There
is no global wallclock / retry / token budget, no built-in guardrail
enforcement, and the lifecycle FSM is adopter-driven. Every one of
these concerns already has a concept elsewhere in the repo:

- `pyarnes-guardrails` ships composable rules but the loop never
  calls them.
- `pyarnes-core` defines a `Lifecycle` FSM but the loop never
  transitions it.
- Adopters have no standard budget type to pass around.

Agents-eval addresses budgets via timeouts and an execution wrapper;
we adopt the **concept** but keep implementation in-repo by adding
three `LoopConfig` fields that default to `None` (no magic, no
behaviour change for existing adopters).

## Goals / non-goals

**Goals.**

- Add `LoopBudget` frozen dataclass to `pyarnes_core.types`.
- Add three optional fields to `LoopConfig`:
  `budget`, `guardrails`, `lifecycle`. All default to `None`.
- Wire them into the existing loop in
  `packages/harness/src/pyarnes_harness/loop.py` without changing
  behaviour when they are `None`.
- Promote `Scorer.score()` to an `async` variant via `Scorer.verdict()`
  (scoped in `bench-scorer-verdict.md`); add `SyncScorer` adapter for
  adopters' existing synchronous code.
- Add `EvalSuite.run_async(scenarios, scorer, concurrency: int = 1)`.

**Non-goals.**

- No new module, no new package. All changes land in
  `pyarnes-core` + `pyarnes-harness` + `pyarnes-bench`.
- No auto-detection of "which budget to apply" — adopter constructs
  and passes the budget explicitly.
- No pause/resume semantics beyond the existing `Lifecycle` states.

## Proposed design

### `LoopBudget` (new, `pyarnes_core.types`)

```python
@dataclass(frozen=True, slots=True)
class LoopBudget:
    max_total_retries: int | None = None
    max_wallclock_s: float | None = None
    max_tokens: int | None = None
```

Any field can be `None` to disable that dimension. All three `None`
is equivalent to "no budget" (caller should pass `None` instead).

### `LoopConfig` — three new optional fields

```python
# packages/harness/src/pyarnes_harness/config.py
budget: LoopBudget | None = None
guardrails: GuardrailChain | None = None
lifecycle: Lifecycle | None = None
```

### Loop integration (minimal, additive)

In `packages/harness/src/pyarnes_harness/loop.py`:

- **Budget**: the existing `_call_tool` retry path already tracks
  retries; add wallclock/token accounting and raise
  `UserFixableError("budget exceeded: <dimension>")` when any limit
  trips. When `budget is None`, zero-cost no-op.

- **Guardrails**: before each tool dispatch, if `guardrails is not None`,
  call `await chain.check(tool_name, args)`. On violation the chain
  raises `LLMRecoverableError` (already defined) so the model sees the
  denial message and adjusts — matches the existing error taxonomy in
  `CLAUDE.md`.

- **Lifecycle**: if `lifecycle is not None`, transition it on
  `start` / `pause` / `complete` / `fail` events. States match the
  FSM in `pyarnes_core.lifecycle`.

All three hooks are strictly additive — the existing loop test suite
passes unchanged.

### Async scorer migration (from `bench-scorer-verdict.md`)

- `Scorer.verdict()` is already `async` in the verdict spec; this
  spec adds:
  - `SyncScorer(Scorer)` wrapper that lets adopters keep a
    synchronous `score()` and still satisfy the async `verdict()`
    default.
  - `EvalSuite.run_async(scenarios, scorer, concurrency: int = 1)`
    using `asyncio.gather` with a semaphore for concurrency.
    Default `1` preserves today's serial behaviour.

### File layout

```
packages/core/src/pyarnes_core/types.py           # add LoopBudget
packages/harness/src/pyarnes_harness/config.py    # add 3 fields
packages/harness/src/pyarnes_harness/loop.py      # wire 3 hooks
packages/bench/src/pyarnes_bench/scorer.py        # SyncScorer
packages/bench/src/pyarnes_bench/suite.py         # run_async
tests/unit/test_loop_budget.py                    # new
tests/features/guardrails_short_circuit.feature   # extended
CHANGELOG.md                                      # Added entry
```

## Tests / acceptance

- `tests/unit/test_loop_budget.py`:
  - `max_total_retries=0` → first failure surfaces as `UserFixableError`.
  - `max_wallclock_s=0.01` with a slow tool → budget trip.
  - `max_tokens=100` with a >100-token response → budget trip.
  - `LoopBudget(None, None, None)` passed explicitly → identical
    behaviour to `budget=None` (documented invariant).

- Extended BDD feature `tests/features/guardrails_short_circuit.feature`:
  - Given a guardrail chain that denies tool `dangerous_op`
  - When the loop attempts `dangerous_op`
  - Then the chain raises `LLMRecoverableError` and the model gets
    the denial as a `ToolMessage`.

- `tests/unit/test_lifecycle_hook.py`:
  - Given `LoopConfig.lifecycle = Lifecycle()`
  - After a successful run, states transitioned are
    `[idle, running, completed]`.
  - After a budget trip, states end with `failed`.

- `tests/unit/test_run_async.py`:
  - `EvalSuite.run_async(..., concurrency=4)` finishes ≤ 1/3 the
    time of `concurrency=1` on a 4-scenario sleepy scorer.

- Stable-surface golden updated for `LoopBudget`, `SyncScorer`,
  and the three `LoopConfig` fields.

- `uv run tasks check` green.

## Reuse

- `GuardrailChain` from `pyarnes_guardrails` — already exists; just
  call `chain.check`.
- `Lifecycle` from `pyarnes_core.lifecycle` — already exists; use
  its public transition API.
- `LLMRecoverableError` / `UserFixableError` from
  `pyarnes_core.errors` — per the taxonomy in `CLAUDE.md`.
- `asyncio.Semaphore` + `asyncio.gather` for concurrency — no
  library addition.

## Risks & rollback

- **Risk:** A guardrail that takes a long time blocks every tool
  call. **Mitigation:** document a 1-second soft timeout on
  `chain.check`; if it trips the loop logs and proceeds (fails open
  for availability, fails closed only on explicit guardrail verdict).
- **Risk:** Budget accounting drifts from real tokens if the model
  client under-reports. **Mitigation:** budget treats missing token
  counts as zero — callers who care pass a `ModelClient` that
  reports.
- **Rollback:** Every new field is `None`-defaulted; removing a
  construction-site `LoopConfig(budget=...)` restores the old
  behaviour. No data migration.

## Exit criteria

- All tests listed above green.
- `uv run tasks check` passes with all three features exercised.
- `docs/adopter/evaluate/lifecycle.md` mentions the new
  `LoopConfig.lifecycle` field.
- `docs/adopter/evaluate/errors.md` cross-references budget-trip
  errors under `UserFixableError`.

## Open questions

- Should `LoopBudget` gain a `max_cost_usd` dimension? **Lean:**
  not yet — `max_tokens` × `cost_per_token` at the adopter layer
  is cheaper than threading USD through the loop.
- Should budget trips emit a loguru log line at `WARNING` or
  `ERROR`? **Lean:** `WARNING` — it is a planned termination, not
  a bug.
- Do we want an `on_budget_exceeded` callback in `LoopConfig` so
  adopters can gracefully flush state before the exception raises?
  **Lean:** defer — the `lifecycle` hook already sees the `failed`
  transition and can be used for flush logic.
