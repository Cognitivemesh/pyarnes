# pyarnes_swarm — Dead Code Audit

## Method

Three-pass audit:
1. **`uv run tasks vulture`** at 60% confidence — flags unused classes, methods, variables
2. **Deep callee analysis** — trace each flagged symbol for external callers via `query_graph`
3. **Cognitive complexity scan** — flag same-concept pairs that differ only in name suffix

## A. Cut entirely — confirmed dead

| Symbol | File | Evidence |
|---|---|---|
| `SeccompSandbox` | `core/sandbox.py` | Linux-only (`prctl` syscall), zero callers outside package export. `SandboxHook` Protocol stays in `ports.py`. |
| `SWEBenchScenario` | `bench/swe_bench.py:29-34` | All 6 fields vulture-flagged. Docstring: "execution deferred to a future milestone." Pure stub with no callers. |
| `_HasScore` Protocol | `guardrails/benchmark_gate.py:35` | Vulture 60%. Replaced by direct `score` attribute access. No callers. |
| `CONSOLE` variable | `core/observe/logger.py:49` | Vulture 60%. Rich console object never used after creation. |
| `METADATA_DEPENDENCIES` | `core/safety/semantic_judge.py:294` | Vulture 60%. Module-level dict populated but never read. |
| `harness/guardrails.py` | whole file | Pure re-export shim. Six lines that alias guardrail symbols from `pyarnes_guardrails`. Disappears when packages merge. |
| `core/packaging/` | whole directory | `version_of()` function + `__version__` re-export machinery. Replaced by `__version__ = "0.1.0"` in the new package. |
| `core/dispatch/ports.py` | whole file | Re-export shim only — all symbols move to `ports.py`. |
| `core/types.py` | whole file | Re-export shim only — all symbols move to `ports.py`. |

## B. Investigate before cutting — dead private methods (vulture 60%)

These were flagged as unused within their own files. They may be called via dynamic dispatch or only from tests. Verify before cutting.

| Symbol | File:line | Action |
|---|---|---|
| `FactEvaluator._validate_counts()` | `bench/fact.py:88` | Check if called in test fixtures. If test-only, inline into the test instead. |
| `RaceEvaluator._normalize_sum()` | `bench/race.py:85` | Verify: may be called by `_compute_score()` indirectly. If truly unused, cut. |
| `RaceEvaluator._validate_alignment()` | `bench/race.py:168` | Same. |
| `model_config` Pydantic internals | `bench/fact.py`, `bench/race.py` | Likely Pydantic v2 internal (`model_config = ConfigDict(...)`). Do NOT cut — Pydantic reads it reflectively. |

## C. Merge — not duplicates, but cognitive complexity pairs

### `compaction.py::CompactionTransformer` + `compressor.py::ContextCompressor`

Both wrap `compact()`. Difference: `ContextCompressor` auto-triggers at 75% capacity; `CompactionTransformer` is always-on. `compressor.py` imports the **private** `_estimate_tokens` from `compaction.py` — a direct coupling smell.

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

### `observe/` + `observability/` directories

Six files across two directories implementing one layered concern. Merge into `observability/` subpackage (4 files). See `01-package-structure.md`.

### `bench/scorer.py` + `bench/scorers.py`

Base classes (`Scorer`, `AsyncScorer`, `ExactMatchScorer`, `LLMJudgeScorer`, `CodeQualityScorer`) in `scorer.py`; trajectory scorers in `scorers.py`. Same ABC, one logical module. Merge into `bench/scorers.py`. Also adds `ScoreResult` (see `07-bench-integrated-axes.md`).

## D. Keep separate — NOT duplicates

### `Budget` (core) vs `IterationBudget` (harness)

These serve different concerns and must never be merged:

| | `Budget` | `IterationBudget` |
|---|---|---|
| Mutability | Immutable (`frozen=True`) | Mutable with `asyncio.Lock` |
| Pattern | Functional value type | Stateful shared counter |
| Returns | New instance on `consume()` | `bool` from async `consume()` |
| Purpose | Per-session caps (calls, seconds, tokens) for Claude Code Stop hooks | Shared step budget across parent + all sub-agents in a swarm |
| `refund()` | No | Yes — sub-agents return unused steps |

They compose: `Budget` tracks what was spent; `IterationBudget` controls how many steps remain.

### Safety module (17 public functions)

All 17 safety functions have verified external callers in guardrails or harness. Nothing to cut.

### `bench/burn/` subpackage

Fully tested and complete. All 10 modules (`classify.py`, `dedupe.py`, `normalize.py`, `kpis.py`, `optimize.py`, `compare.py`, `types.py`, `provider.py`, `costing.py`, `claude_code.py`) have test coverage. Keep intact — move verbatim to `pyarnes_swarm.bench.burn`.

## E. Inline — too small to justify a module

| Source | Destination | Reason |
|---|---|---|
| `dispatch/action_kind.py` | `agent.py` | 3-value enum + `classify()`. Single caller: `AgentLoop`. |
| `dispatch/retry_policy.py` | `agent.py` | `RetryPolicy` dataclass + `next_delay()`. Single caller. |
| `session_id.py` | `agent.py` | Single `new_session_id()` helper function. |
| `harness/classifier.py` | `agent.py` | `ClassifiedError` + `classify_error()`. Single caller: `AgentLoop._handle_error`. |
| `harness/transform.py` (Protocol only) | `ports.py` | `MessageTransformer` Protocol belongs with contracts. `TransformChain` moves to `agent.py`. |

## F. Relocate — wrong home

| Symbol | From | To | Reason |
|---|---|---|---|
| `ToolHandler`, `ModelClient`, `JudgeClient` | `core/dispatch/ports.py` | `ports.py` | Contracts, not dispatch logic |
| `LoggerPort` | `core/observability/ports.py` | `ports.py` | Centralise all contracts |
| `GuardrailPort` | `core/safety/ports.py` | `ports.py` | Same |
| `SecretStore` (new) | — | `ports.py` | New Protocol; belongs with other contracts |

## Design rule

**One concept = one name = one class = one file location.**

Any pair of names that differ only by a suffix (`-er`, `-or`, `-Transformer`, `-Compressor`, `er`/`or`) should trigger a review: are these the same concept? If yes, merge. If no, document why they are distinct.
