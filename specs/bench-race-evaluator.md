# bench-race-evaluator

Contract for the post-hoc RACE (Reference-based Adaptive Criteria-driven
Evaluation) evaluator shipped in `pyarnes-bench`.

Mirrors the style of `specs/bench-scorer-verdict.md`.

## Context

`pyarnes-bench` ships exact-match scoring plus the `Scorer`/`EvalResult`/
`EvalSuite` primitives. It does not cover long-form research-report
evaluation. DeepResearch Bench introduced **RACE** — a validated,
reference-normalized, LLM-as-judge framework that scores a finished
target report against a finished reference across four dynamically
weighted dimensions (comprehensiveness, depth, instruction following,
readability) and achieves ~71 % pairwise agreement with human judges.

This spec ships RACE as a **pure library addition**. No agent
orchestration, no URL fetching, no internal concurrency. Adopters wire
the evaluator into their own `pytest` suite, `tasks bench` target, or
CI harness after the agent has finished producing its report. All
Claude-Code-specific packaging is explicitly deferred to
`specs/claudecode-pyarnes-judge-plugin.md`.

## Goals / non-goals

**Goals.**

- Ship `RaceEvaluator` in `packages/bench/src/pyarnes_bench/race.py`.
- Ship Pydantic v2 result models: `RaceScore`, `RaceWeights`,
  `RaceCriterion`, `RacePrompts`, `RaceDimension`.
- Provide `RaceScore.to_eval_result(scenario, threshold)` so results
  flow into `EvalSuite` unchanged.
- Share the judge-helper (`judge_json`) and citation utilities
  (`strip_markers`, `URL_RE`) in private modules for later reuse by
  FACT.
- Add `pydantic>=2.6` to `packages/bench/pyproject.toml`.
- Update the stable-surface golden test.

**Non-goals.**

- No `Scorer` subclass. `Scorer.score` returns a bare float; the RACE
  verdict is irreducibly richer and the judge call is async.
- No URL fetching, no network I/O, no caching layer.
- No concurrent judge calls (no `asyncio.gather`, `TaskGroup`, or
  `Semaphore`). Evaluators match the serial-by-design convention of
  `packages/harness/src/pyarnes_harness/loop.py`.
- No composite / weighted evaluator — adopters compose explicitly.
- No fixtures or example data bundled in `packages/bench/src/`.
- No Claude Code plug-in — deferred to the spec above.

## Proposed design

### `RaceDimension` (enum)

Four members: `COMPREHENSIVENESS`, `DEPTH`, `INSTRUCTION_FOLLOWING`,
`READABILITY`. Inherits `str` so `.value` is a usable prompt token.

### `RaceWeights` (Pydantic `BaseModel`, `frozen=True`, `extra="forbid"`)

```python
class RaceWeights(BaseModel):
    weights: dict[RaceDimension, float]  # each in [0, 1]

    @model_validator(mode="after")
    def _validate_sum(self) -> Self:
        # Reject sums below a small floor; renormalize minor drift.
        ...
```

Values in `[0, 1]`. Sum must be in `[_WEIGHT_RENORM_FLOOR, ∞)`; within
`1 ± _WEIGHT_SUM_TOLERANCE` is kept as-is, otherwise re-normalized to
exactly 1. Rejects all-zero inputs.

### `RaceCriterion` (Pydantic `BaseModel`)

```python
class RaceCriterion(BaseModel):
    dimension: RaceDimension
    text: str  # non-empty
    weight: float  # in [0, 1]
```

Per-dimension criterion weights sum to 1 (enforced in
`RaceEvaluator._judge_criteria`, not on the model itself — the model
stores one criterion at a time).

### `RacePrompts` (Pydantic `BaseModel`, all fields have defaults)

Three overridable prompt templates (`weighting_prompt`,
`criteria_prompt`, `scoring_prompt`) using `str.format` placeholders.
Module-level `_DEFAULT_*` constants hold the defaults. Literal braces
in JSON-schema hints are escaped as `{{` / `}}`.

### `RaceScore` (Pydantic `BaseModel`, `frozen=True`, `extra="forbid"`)

```python
class RaceScore(BaseModel):
    weights: RaceWeights
    criteria: tuple[RaceCriterion, ...]
    per_criterion_target: tuple[float, ...]     # aligned with criteria
    per_criterion_reference: tuple[float, ...]  # aligned with criteria
    internal_target: float      # in [0, 1]
    internal_reference: float   # in [0, 1]
    final_score: float          # in [0, 1]
    metadata: dict[str, Any]

    def to_eval_result(self, *, scenario: str, threshold: float = 0.5) -> EvalResult: ...
```

`@model_validator` enforces that the two per-criterion arrays align
with `criteria`.

### `RaceEvaluator`

```python
class RaceEvaluator:
    def __init__(
        self,
        client: ModelClient,
        *,
        prompts: RacePrompts | None = None,
        trials: int = 3,
        dimensions: tuple[RaceDimension, ...] = tuple(RaceDimension),
    ) -> None: ...

    async def evaluate(
        self,
        *,
        task_prompt: str,
        target_report: str,
        reference_report: str,
    ) -> RaceScore: ...
```

Flow, one `await` at a time:

1. Strip citation markers from both reports with `_citations.strip_markers`.
2. Average `trials` weighting-judge calls → `RaceWeights`.
3. For each dimension in order, one criteria-judge call → list of
   `RaceCriterion` whose weights are renormalized to sum to 1.
4. For each `(dimension, criterion)` pair in order, one judge call for
   the target then one for the reference.
5. Aggregate `S_int(r) = Σ_d w_d · Σ_c w_{d,c} · s_{d,c,r}`; compute
   `final_score = S_int(target) / (S_int(target) + S_int(reference))`
   (0.5 when both are zero).
6. Log JSONL via `pyarnes_core.observe.logger.get_logger`.

### File layout

```
packages/bench/src/pyarnes_bench/
  race.py              # NEW  — all public RACE symbols
  _citations.py        # NEW  — private utilities (also for FACT)
  _judge.py            # NEW  — private JSON-validating judge helper
  __init__.py          # EDIT — re-exports
tests/unit/bench/
  test_race.py         # NEW
  test_citations.py    # NEW
  test_judge.py        # NEW
tests/features/
  race_evaluation.feature          # NEW
  steps/test_race_evaluation.py    # NEW
tests/unit/test_stable_surface.py  # EDIT — add new symbols
specs/bench-race-evaluator.md      # NEW (this file)
CHANGELOG.md                       # EDIT — Added entry
packages/bench/pyproject.toml      # EDIT — pydantic>=2.6
docs/adopter/build/benchmarking.md # EDIT — "Deep-research evaluation"
docs/maintainer/packages/bench.md  # EDIT — diagram + API table row
packages/bench/README.md           # EDIT — one-line mention
```

## Error taxonomy mapping

| Source                                               | Error raised              |
|------------------------------------------------------|---------------------------|
| Empty `task_prompt` / `target_report` / `reference`  | `UserFixableError`        |
| Judge returns non-JSON or fails Pydantic validation  | `LLMRecoverableError` (after one internal retry) |
| Judge produces criteria with non-positive weight sum | `UserFixableError`        |
| Weights below `_WEIGHT_RENORM_FLOOR`                 | `ValidationError` → surfaces as `UnexpectedError` at the call site |
| Provider rate-limit / network                        | `TransientError` (bubbles from the `ModelClient`) |

## Tests / acceptance

- `tests/unit/bench/test_race.py`:
  - Identical target and reference yield `final_score == 0.5`.
  - Target rated higher than reference yields `final_score > 0.5`.
  - Criteria weights per dimension sum to 1 after normalization.
  - `final_score` always in `[0, 1]` (direct plus Hypothesis property).
  - `RaceScore.to_eval_result` threshold routing.
  - Empty target / empty reference → `UserFixableError`.
  - Persistently malformed judge output → `LLMRecoverableError`.
  - `trials < 1` rejected at construction time.
  - Per-criterion score arrays must align with `criteria` tuple.
- `tests/unit/bench/test_citations.py`: numeric, author-year, ranged,
  multiple, multiline markers; idempotency; URL regex on typical cases
  including trailing punctuation.
- `tests/unit/bench/test_judge.py`: plain JSON, fenced-JSON,
  `content: {text: ...}` variant, retry-once-on-bad-JSON, failure path
  raises `LLMRecoverableError`, missing-content path.
- `tests/features/race_evaluation.feature` + steps: three scenarios
  covering the identical / better-target / empty-target paths.
- `tests/unit/test_stable_surface.py` now lists every new public
  symbol.
- `uv run tasks check` and `uv run tasks security` both clean.

## Open questions

- Should the weighting prompt ask for a rationale? **Lean:** no — the
  paper's prompt only asks for weights, keeping parsing narrow.
- Should the criteria judge see the reference report too? **Lean:**
  no — criteria should be task-driven, not target-driven, to avoid
  circular "reference was great because it covered X" criteria.
- Should `RaceWeights` fail hard on sums outside `1 ± tolerance`
  instead of re-normalizing? **Lean:** no — LLM judges drift by a few
  hundredths; silent re-normalization is the ergonomic choice and the
  original total is recoverable from trial-level logs.
