# pyarnes_swarm — Dead Code Audit

> **Spec header**
>
> | Field | Value |
> |---|---|
> | **Title** | pyarnes_swarm — Dead Code Audit |
> | **Status** | active |
> | **Type** | testing |
> | **Tags** | cleanup, audit, complexity, refactor |
> | **Owns** | dead-code audit policy, three-pass method (vulture → callee trace → cognitive complexity), cut/keep ledger, stable-surface cleanup process |
> | **Depends on** | 01-package-structure.md, 02-test-strategy.md, 03-test-map.md |
> | **Extends** | — |
> | **Supersedes** | — |
> | **Read after** | 03-test-map.md |
> | **Read before** | 17-tooling-artifacts.md |
> | **Not owned here** | TDD discipline (see `02-test-strategy.md`); test migration map (see `03-test-map.md`); tooling exclusions (see `17-tooling-artifacts.md`); error taxonomy definitions (see `01-package-structure.md`) |
> | **Last reviewed** | 2026-04-29 |

## Design Rationale

**Why delete dead code before implementation instead of after?** Porting dead code wastes effort and creates confusion — future maintainers can't tell if a class is intentionally unused or accidentally orphaned. Auditing first ensures that Phase 1 tests are written only for code that will actually exist in the consolidated package.

**Why keep `Budget` and `IterationBudget` as separate classes?** They look similar but are fundamentally different data structures:
- `Budget` (`frozen=True`) is an **immutable value type** — `consume()` returns a *new* `Budget` with updated counts. Used by Claude Code Stop hooks to record session spend as a snapshot.
- `IterationBudget` is a **mutable shared counter** with `asyncio.Lock` — `consume()` modifies shared state and returns `bool`. Used across parent and sub-agents in a live swarm.
Merging them would produce a class that is simultaneously immutable (for value semantics) and mutable (for shared state) — a contradiction that cannot be resolved without one of them losing its defining property.

**Why is the cognitive complexity scan a separate pass from vulture?** Vulture finds unused code. The cognitive complexity scan finds *duplicated* concepts — two classes that implement the same idea with slightly different names. These aren't dead code (both are used), but they create confusion about which to reach for. Example: `CompactionTransformer` and `ContextCompressor` both wrap `compact()` — one always-on, one threshold-triggered. Two names for one concept → one class (`MessageCompactor`) with a `context_window` parameter.

## Specification

### Method

> **Diagram:** [Dead-code audit lifecycle](diagrams/04-dead-code-lifecycle.html). Three-pass audit funneling each symbol into one of four terminal outcomes (cut · merged · kept · relocated).

Three-pass audit:
1. **`uv run tasks vulture`** at 60% confidence — flags unused classes, methods, variables
2. **Deep callee analysis** — trace each flagged symbol for external callers via `query_graph`
3. **Cognitive complexity scan** — flag same-concept pairs that differ only in name suffix

### Current repo review

This spec mixes **current-repo evidence** with **target-package cleanup**. Those are not the same thing. In the current monorepo, the symbols below are the ones that are truly inactive-or-easy-to-lose because they are exported and tested, but not actually adopted by a shipped runtime path.

| Symbol / area | Current status | Why it is not used in runtime today | How to avoid losing it |
|---|---|---|---|
| `SeccompSandbox` | Package export + unit tests only | `AgentLoop` supports `sandbox=...`, but no template hook, runtime helper, or scaffold shape ever passes one. | Either cut it, or add an opt-in `AgentRuntime.with_sandbox(...)` / template toggle for Linux CI runners. |
| `SWEBenchScenario` | Package export only | The module is intentionally DTO-only; no loader, provider, or evaluator currently constructs it. | Keep only if a future SWE-bench provider/fixture loader consumes it; otherwise move the shape into the spec until execution lands. |
| `ASTGuardrail` | Export + unit tests only | The shipped Claude Code hook chain does path/command/secret/network/rate-limit checks, but never scans code payloads. | Add it to the pre-tool hook when the allowlisted tools can carry source payloads (`Write`, `Edit`, notebook/code cells, etc.). |
| `BenchmarkGateGuardrail` | Export + unit tests only | The async guardrail exists, but no template or verification path composes it into a live chain. | Wire it into a promotion gate or `VerificationLoop` callback where a scored suite already exists. |
| `CompactionTransformer` | Export + one unit test | `ContextCompressor` is the runtime-adopted wrapper; both call `compact()`, but only the threshold-based wrapper is composed by default. | Either document `TransformChain([CompactionTransformer(...)])` as the always-on path, or merge it with `ContextCompressor`. |
| `CompactionConfig.reserve_tokens` | Stored-only field | The current cut-finder and threshold checks never subtract response headroom from the effective window. | Either remove it or make compaction math use `context_window - reserve_tokens`. |
| `ModelAlias.family` | Stored-only field | Alias resolution returns the canonical model id, but KPI/report code derives family elsewhere instead of reading the field. | Either remove it or use it directly in burn KPI grouping/reporting. |
| `core/packaging/version_of()` | Live helper in the current monorepo | Every package `__init__` still uses it to derive `__version__`; it is only deletable after the single-package merge. | Keep it for the split-package repo; revisit only when consolidation actually removes per-package version shims. |

These are **false positives** from static “unused code” checks and should not be cut:

- `FactMetrics._validate_counts()`, `RaceWeights._normalize_sum()`, and `RaceScore._validate_alignment()` are Pydantic `@model_validator(mode="after")` hooks. Reference search sees only the definition, but Pydantic calls them reflectively during model construction.
- `METADATA_DEPENDENCIES` inside the `_LibCSTVisitor` in `semantic_judge.py` is a `libcst` metadata contract, not orphaned state.
- `LogFormat.CONSOLE` is a public enum branch of the logging API, not the old unused Rich console object that an earlier audit referred to.

### A. Cut entirely — confirmed dead

| Symbol | File | Evidence |
|---|---|---|
| `SeccompSandbox` | `core/sandbox.py` | Linux-only (`prctl` syscall), zero callers outside package export. `SandboxHook` Protocol stays in `ports.py`. |
| `SWEBenchScenario` | `bench/swe_bench.py:29-34` | All 6 fields vulture-flagged. Docstring: "execution deferred to a future milestone." Pure stub with no callers. |
| `_HasScore` Protocol | `guardrails/benchmark_gate.py:35` | Vulture 60%. Replaced by direct `score` attribute access. No callers. |
| `harness/guardrails.py` | whole file | Pure re-export shim. Six lines that alias guardrail symbols from `pyarnes_guardrails`. Disappears when packages merge. |
| `core/dispatch/ports.py` | whole file | Re-export shim only — all symbols move to `ports.py`. |
| `core/types.py` | whole file | Re-export shim only — all symbols move to `ports.py`. |

### B. Cut export-only APIs — no production callers

Aggressive stance for consolidation: a symbol that is referenced only by package exports, stable-surface tests, or unit tests is treated as dead unless another consolidation spec gives it a concrete retained role.

| Symbol | File | Evidence |
|---|---|---|
| `ASTGuardrail` | `guardrails/guardrails.py` | `rg` finds only the class definition, package re-export, and unit tests. No harness/runtime wiring and no consolidation spec depends on it. |
| `BenchmarkGateGuardrail` | `guardrails/benchmark_gate.py` | Referenced only by package export, unit tests, docstring example, and `03-test-map.md`. No production caller and no guardrail chain wiring. |

### C. Investigate before cutting — dead private methods (vulture 60%)

These look unused to static scanners because the calls are reflective rather than lexical. They should stay.

| Symbol | File:line | Action |
|---|---|---|
| `FactMetrics._validate_counts()` | `bench/fact.py:88` | Keep — Pydantic `@model_validator(mode="after")`; called reflectively during model construction. |
| `RaceWeights._normalize_sum()` | `bench/race.py:85` | Keep — Pydantic `@model_validator(mode="after")`; renormalises judge-produced weights. |
| `RaceScore._validate_alignment()` | `bench/race.py:168` | Keep — Pydantic `@model_validator(mode="after")`; validates per-criterion array alignment. |
| `model_config` Pydantic internals | `bench/fact.py`, `bench/race.py` | Keep — reflective Pydantic config (`ConfigDict(...)`), not dead code. |

### D. Remove dead fields — stored but never consumed

These are not dead modules, but dead fields/config knobs that should not survive the merge.

| Symbol | File | Action |
|---|---|---|
| `CompactionConfig.reserve_tokens` | `harness/compaction.py:37` | Docstring already says "unused". No reads exist because neither `_find_cut_index()` nor `ContextCompressor` subtract response headroom today. Remove it unless a later token-budget spec starts consuming it for real context-window accounting. |
| `ModelAlias.family` | `bench/burn/normalize.py:98` | Constructed in defaults but never read; KPI code derives family elsewhere. Remove it unless a report or grouping path starts consuming family directly from aliases. |

### E. Merge — not duplicates, but cognitive complexity pairs

#### `compaction.py::CompactionTransformer` + `compressor.py::ContextCompressor`

Both wrap `compact()`. Difference: `ContextCompressor` auto-triggers at 75% capacity; `CompactionTransformer` is always-on. `compressor.py` imports the **private** `_estimate_tokens` from `compaction.py` — a direct coupling smell.

Current repo status: the split is asymmetrical. `ContextCompressor` is the only wrapper that is actually composed by a shipped runtime path (`AgentRuntime.with_compressor()`), while `CompactionTransformer` is only exported and unit-tested. That makes the always-on adapter the easier one to lose during consolidation unless it is either documented as the explicit `TransformChain` path or folded into the same public type.

**Fix:** Merge into `MessageCompactor` in `agent.py`:

```python
@dataclass
class MessageCompactor:
    """Wraps compact(). If context_window is set, fires only above capacity_threshold.
    If context_window is None, always compacts."""
    model: ModelClient
    context_window: int | None = None
    capacity_threshold: float = 0.75
    config: CompactionConfig = field(default_factory=CompactionConfig)

    async def __call__(self, messages: list[dict]) -> list[dict]:
        if self.context_window is not None:
            used = _estimate_tokens(messages, self.config.tokens_per_char)
            if used < self.context_window * self.capacity_threshold:
                return messages
        return await compact(messages, self.model, self.config)
```

Delete `compressor.py`. One class, one name, one file.

#### `observe/` + `observability/` directories

Six files across two directories implementing one layered concern. Merge into `observability/` subpackage (4 files). See `01-package-structure.md`.

#### `bench/scorer.py` + `bench/scorers.py`

Base classes (`Scorer`, `AsyncScorer`, `ExactMatchScorer`, `LLMJudgeScorer`, `CodeQualityScorer`) in `scorer.py`; trajectory scorers in `scorers.py`. Same ABC, one logical module. Merge into `bench/scorers.py`. Also adds `ScoreResult` (see `15-bench-integrated-axes.md`).

### F. Keep separate — NOT duplicates

#### `Budget` (core) vs `IterationBudget` (harness)

These serve different concerns and must never be merged:

| | `Budget` | `IterationBudget` |
|---|---|---|
| Mutability | Immutable (`frozen=True`) | Mutable with `asyncio.Lock` |
| Pattern | Functional value type | Stateful shared counter |
| Returns | New instance on `consume()` | `bool` from async `consume()` |
| Purpose | Per-session caps (calls, seconds, tokens) for Claude Code Stop hooks | Shared step budget across parent + all sub-agents in a swarm |
| `refund()` | No | Yes — sub-agents return unused steps |

They compose: `Budget` tracks what was spent; `IterationBudget` controls how many steps remain.

#### Safety module (17 public functions)

All 17 safety functions have verified external callers in guardrails or harness. Nothing to cut.

#### `bench/burn/` subpackage

Fully tested and complete. All 10 modules (`classify.py`, `dedupe.py`, `normalize.py`, `kpis.py`, `optimize.py`, `compare.py`, `types.py`, `provider.py`, `costing.py`, `claude_code.py`) have test coverage. Keep intact — move verbatim to `pyarnes_swarm.bench.burn`.

### G. Keep despite zero callers

| Symbol | File | Why it stays |
|---|---|---|
| `AgentRuntime.with_compressor()` | `harness/runtime.py:175` | No current code callers, but `08-token-budget.md` promotes it as the adopter-facing one-liner API. Public convenience API, not dead code. |

### H. Inline — too small to justify a module

| Source | Destination | Reason |
|---|---|---|
| `dispatch/action_kind.py` | `agent.py` | 3-value enum + `classify()`. Single caller: `AgentLoop`. |
| `dispatch/retry_policy.py` | `agent.py` | `RetryPolicy` dataclass + `next_delay()`. Single caller. |
| `session_id.py` | `agent.py` | Single `new_session_id()` helper function. |
| `harness/classifier.py` | `agent.py` | `ClassifiedError` + `classify_error()`. Single caller: `AgentLoop._handle_error`. |
| `harness/transform.py` (Protocol only) | `ports.py` | `MessageTransformer` Protocol belongs with contracts. `TransformChain` moves to `agent.py`. |

### I. Relocate — wrong home

| Symbol | From | To | Reason |
|---|---|---|---|
| `ToolHandler`, `ModelClient`, `JudgeClient` | `core/dispatch/ports.py` | `ports.py` | Contracts, not dispatch logic |
| `LoggerPort` | `core/observability/ports.py` | `ports.py` | Centralise all contracts |
| `GuardrailPort` | `core/safety/ports.py` | `ports.py` | Same |
| `SecretStore` (new) | — | `ports.py` | New Protocol; belongs with other contracts |

### J. Stable-surface cleanup

Dead-code cuts that touch exported symbols must update compatibility declarations in the same change. Otherwise the repository ends up with a spec that says "delete this" while `CHANGELOG.md` and `tests/unit/test_stable_surface.py` still enforce that it exists.

Minimum compatibility cleanup set already implied by this audit:

- Remove `SeccompSandbox` from the declared stable surface when it is cut.
- Remove `SWEBenchScenario` from the declared stable surface when it is cut.
- Remove `ASTGuardrail` and `BenchmarkGateGuardrail` from the declared stable surface if the aggressive export-only cut is applied.

Companion test/doc changes that should happen with the code deletion:

- Delete or rewrite `tests/unit/test_benchmark_gate.py`.
- Delete or rewrite `tests/unit/safety/test_ast_deep.py`.
- Update any stable-surface assertions that still require removed exports.
- If the removed symbol carried a user-visible workflow, move that workflow's contract into `tests/features/` before deleting the old runtime test.

### Design rule

**One concept = one name = one class = one file location.**

Any pair of names that differ only by a suffix (`-er`, `-or`, `-Transformer`, `-Compressor`, `er`/`or`) should trigger a review: are these the same concept? If yes, merge. If no, document why they are distinct.
