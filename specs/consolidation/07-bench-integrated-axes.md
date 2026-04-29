# pyarnes_swarm — Bench: Integrated Evaluation Axes

> **Spec header**
>
> | Field | Value |
> |---|---|
> | **Title** | pyarnes_swarm — Bench (Evaluation Axes) |
> | **Status** | active |
> | **Type** | evaluation-capture |
> | **Owns** | Scorer ABC, ScoreResult, EvalResult, EvalSuite.run(), CostCalculator, RACE evaluator, FACT evaluator, use-case taxonomy (Tier 1/2/3), efficiency feedback loop closure |
> | **Depends on** | 04-swarm-api.md, 12-token-budget.md |
> | **Extends** | 13-run-logger.md, 18-evaluation-taxonomy.md |
> | **Supersedes** | bench-fact-evaluator.md, bench-race-evaluator.md, bench-scorer-verdict.md, bench-use-cases-coding-and-deep-agents.md |
> | **Read after** | 11-secrets.md |
> | **Read before** | 13-run-logger.md |
> | **Not owned here** | error taxonomy definitions (see `01-package-structure.md`); recovery semantics (see `04-swarm-api.md`); run persistence schema (see `13-run-logger.md`); model routing (see `03-model-router.md`); evaluation-taxonomy reference appendix (see `18-evaluation-taxonomy.md`); graph-based scorers (see `23-graph-package.md`) |
> | **Last reviewed** | 2026-04-29 |

## Design Rationale

**Why does `Scorer.score()` return `ScoreResult` instead of a `float`?** An `LLMJudgeScorer` makes its own LLM call to evaluate quality. That call has a cost. If the scorer returns only a `float`, you know the quality score but not how much the evaluation itself cost. Over many eval runs, evaluation cost can approach or exceed agent cost — ignoring it produces false economy. `ScoreResult.usage` makes evaluation cost visible so `EvalSuite.run()` can include it in the total.

**Why is `EvalSuite.run()` the integration point instead of the scorer or BurnTracker?** The scorer knows quality. BurnTracker knows cost. `EvalSuite.run()` is the only place that sees both simultaneously — it's the natural place to join them. If the join were in the scorer, scorers would need to import BurnTracker (coupling quality logic to cost infrastructure). If it were in BurnTracker, cost tracking would need to know about quality scoring. `EvalSuite` is the coordinator that knows about both without coupling them.

**Why does the efficiency feedback loop close back to `LLMCostRouter`?** Without feedback, routing is static — you set tiers once and they never change. With feedback, a cheap model that consistently scores well on a task type gets promoted (its complexity ceiling raised). The evaluation system isn't just a report card; it's the signal that makes routing self-improving.

## The problem

`EvalResult` already has `usage: TokenUsage | None` and `cost: Cost | None`. `EvalSuite` already has `cost_efficiency = average_score / total_cost`. The foundation is there — but `Scorer.score()` returns a bare `float`, and there is no integration point that connects `BurnTracker` to scoring automatically. The three axes are manually assembled by callers.

```
Scorer.score() ──► float only     ← no usage, no cost
BurnTracker    ──► separate call  ← caller must manually join
EvalResult     ──► usage/cost fields always None unless caller populates them
```

## The redesign

### `ScoreResult` — quality + token evidence

```python
@dataclass(frozen=True)
class ScoreResult:
    """Quality + optional token evidence from the scoring step itself."""
    score: float                     # 0.0 – 1.0
    usage: TokenUsage | None = None  # tokens the scorer spent (e.g. LLM judge)
    passed: bool | None = None       # if None, caller applies threshold
```

### Updated `Scorer` ABC  *(breaking change — return type changes from `float` to `ScoreResult`)*

```python
class Scorer(ABC):
    @abstractmethod
    async def score(
        self,
        expected: Any,
        actual: Any,
        *,
        scenario: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ScoreResult: ...

class AsyncScorer(ABC):  # alias kept for backwards compat during migration
    @abstractmethod
    async def score(self, expected: Any, actual: Any, **kwargs: Any) -> ScoreResult: ...
```

`ExactMatchScorer` returns `ScoreResult(score=1.0/0.0, usage=None)`.
`LLMJudgeScorer` returns `ScoreResult(score=..., usage=<judge_call_usage>)`.
`CodeQualityScorer` returns `ScoreResult(score=..., usage=None)`.

### `EvalResult` — full schema

```python
@dataclass(frozen=True)
class EvalResult:
    scenario: str
    expected: Any
    actual: Any
    score: float               # 0.0 – 1.0
    passed: bool               # score >= threshold (threshold set at EvalSuite.run() call)
    usage: TokenUsage | None = None   # combined agent + scorer token usage
    cost: Cost | None = None          # None when no CostCalculator provided
```

`TokenUsage` and `Cost` are imported from `pyarnes_swarm.bench.burn.types`. `Cost` carries `amount: Decimal` and `currency: str` (e.g. `"EUR"`).

The `run_id`, `started_at`, and `finished_at` fields are additive; see `13-run-logger.md` for the extended schema that ties evaluation rows to a run.

### `CostCalculator` Protocol

```python
class CostCalculator(Protocol):
    """Converts token usage into a monetary cost. Lives in bench/burn/costing.py."""
    def compute(self, usage: TokenUsage) -> Cost: ...
```

The concrete implementation is `LiteLLMCostCalculator` in `bench/burn/costing.py` — already implemented, no changes needed.

### `EvalSuite.run()` — the integration point

```python
class EvalSuite:
    async def run(
        self,
        scenario: str,
        expected: Any,
        actual: Any,
        *,
        scorer: Scorer,
        agent_usage: TokenUsage | None = None,   # tokens from the agent run
        cost_calculator: CostCalculator | None = None,
        threshold: float = 0.5,
    ) -> EvalResult:
        result = await scorer.score(expected, actual, scenario=scenario)

        # Combine agent usage + scorer's own token usage
        total_usage = (agent_usage or TokenUsage()) + (result.usage or TokenUsage())
        cost = (
            cost_calculator.compute(total_usage)
            if cost_calculator and total_usage.total > 0
            else None
        )

        eval_result = EvalResult(
            scenario=scenario,
            expected=expected,
            actual=actual,
            score=result.score,
            passed=result.score >= threshold,
            usage=total_usage if total_usage.total > 0 else None,
            cost=cost,
        )
        self.add(eval_result)
        return eval_result
```

Callers no longer manually plumb token counts or costs. `EvalSuite.run()` is the single integration point.

### Efficiency feedback to `LLMCostRouter`

`EvalSuite.cost_efficiency` (already exists: `average_score / total_cost * 100`) becomes the routing feedback signal:

```python
# After a suite run, report to the router
efficiency = suite.cost_efficiency
router.observe(
    model_id="claude-haiku-4-5-20251001",
    task_type="summarise",
    efficiency=efficiency,
)
```

This closes the loop:

```
AgentSpec (complexity_hint)
    │
    ▼
LLMCostRouter.route() → model_id
    │
    ▼
LiteLLMModelClient → agent run → actual output + TokenUsage
    │
    ▼
EvalSuite.run(scorer, agent_usage=...) → EvalResult(score, usage, cost)
    │
    ▼
suite.cost_efficiency → router.observe(model_id, task_type, efficiency)
    │
    ▼  (next routing decision for this task_type uses updated weights)
LLMCostRouter.route()
```

Cheap models that score well on a task type get promoted (complexity ceiling raised). Expensive models that underperform get demoted.

## What the scorer IS (clarified)

| Old understanding | Redesigned role |
|---|---|
| Returns `float` for pass/fail gating | Returns `ScoreResult` with quality + token evidence |
| Separate from cost tracking | `EvalSuite.run()` joins scorer output with BurnTracker |
| Report metric only | Feedback signal → `LLMCostRouter` efficiency learning |
| Three unlinked systems | One pipeline: Scorer → EvalResult(quality, cost, efficiency) → Router |

## `codeburn` integration

The existing `codeburn` KPI pipeline (from `bench/burn/`) tracks token usage from Claude Code transcripts. `EvalSuite.run()` complements this: it tracks token usage from **programmatic agent runs** (not just Code sessions).

Both pipelines write to `BurnTracker` → `CostCalculator` → `EvalResult.cost`. The health grade from `codeburn:optimize` and the `cost_efficiency` from eval runs are comparable metrics — both measure quality-per-token.

## Quick start

```python
import asyncio
from pyarnes_swarm.bench import EvalSuite, ScoreResult
from pyarnes_swarm.bench.scorers import ExactMatchScorer, LLMJudgeScorer
from pyarnes_swarm.bench.burn.costing import LiteLLMCostCalculator
from pyarnes_swarm.bench.burn.types import TokenUsage

scorer = ExactMatchScorer()
calculator = LiteLLMCostCalculator()
suite = EvalSuite(name="summarisation")

# Simulate: agent used 500 tokens to produce the response
agent_usage = TokenUsage(input_tokens=400, output_tokens=100)

result = asyncio.run(suite.run(
    scenario="short-summary",
    expected="The file contains a readfile tool.",
    actual="The file contains a readfile tool.",
    scorer=scorer,
    agent_usage=agent_usage,
    cost_calculator=calculator,
))

print(result.score)            # 1.0
print(result.cost)             # Cost(amount=..., currency="EUR")
print(suite.cost_efficiency)   # average_score / total_cost * 100
```

## RACE and FACT evaluators

RACE and FACT are post-hoc, sequential evaluators. They do **not** subclass `Scorer` — their verdicts are richer than a single float and their judge calls are async. They bridge into `EvalSuite` via `to_eval_result()`, which builds an `EvalResult` directly and carries the accumulated judge usage in `EvalResult.usage`. Callers who want the result included in `EvalSuite` totals pass it to `suite.add()` manually — it does not flow through `suite.run()`.

### Shared internals — `pyarnes_swarm.bench._judge`

`judge_json`, `strip_markers`, and `URL_RE` all live in the private module `pyarnes_swarm.bench._judge`. Both `RaceEvaluator` and `FactEvaluator` import from there; adopters should not import this module directly.

---

### `RaceEvaluator` — `pyarnes_swarm.bench.race`

> **Diagram:** [RACE four-dimension scoring](diagrams/07-race-scoring.html). Four dimensions (comprehensiveness · depth · instruction following · readability) feed into `internal_target` / `internal_reference`; the weighted aggregate is `final_score ∈ [0, 1]`.

RACE (Reference-based Adaptive Criteria-driven Evaluation) scores a finished target report against a finished reference report across four dynamically weighted dimensions. It achieves ~71 % pairwise agreement with human judges.

#### `RaceDimension` (enum)

```python
class RaceDimension(str, Enum):
    COMPREHENSIVENESS = "comprehensiveness"
    DEPTH = "depth"
    INSTRUCTION_FOLLOWING = "instruction_following"
    READABILITY = "readability"
```

Inherits `str` so `.value` is a usable prompt token.

#### `RaceWeights` (Pydantic `BaseModel`, `frozen=True`, `extra="forbid"`)

```python
class RaceWeights(BaseModel):
    weights: dict[RaceDimension, float]  # each in [0, 1]

    @model_validator(mode="after")
    def _validate_sum(self) -> Self:
        # Reject sums below a small floor; renormalize minor drift.
        ...
```

Values in `[0, 1]`. Sum must be in `[_WEIGHT_RENORM_FLOOR, ∞)`; within `1 ± _WEIGHT_SUM_TOLERANCE` is kept as-is, otherwise re-normalized to exactly 1. Rejects all-zero inputs.

#### `RaceCriterion` (Pydantic `BaseModel`)

```python
class RaceCriterion(BaseModel):
    dimension: RaceDimension
    text: str   # non-empty
    weight: float  # in [0, 1]
```

Per-dimension criterion weights sum to 1 (enforced in `RaceEvaluator._judge_criteria`, not on the model itself — the model stores one criterion at a time).

#### `RaceScore` (Pydantic `BaseModel`, `frozen=True`, `extra="forbid"`)

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

A `@model_validator` enforces that the two per-criterion arrays align with `criteria`.

#### `RaceEvaluator`

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

Evaluation flow (one `await` at a time — no concurrent judge calls):

1. Strip citation markers from both reports via `_judge.strip_markers`.
2. Average `trials` weighting-judge calls → `RaceWeights`.
3. For each dimension in order, one criteria-judge call → list of `RaceCriterion` whose weights are renormalized to sum to 1.
4. For each `(dimension, criterion)` pair in order, one judge call for the target then one for the reference.
5. Aggregate `S_int(r) = Σ_d w_d · Σ_c w_{d,c} · s_{d,c,r}`; compute `final_score = S_int(target) / (S_int(target) + S_int(reference))` (0.5 when both are zero).
6. Log JSONL via `pyarnes_swarm.observability.get_logger`.

`RacePrompts` carries three overridable prompt templates (`weighting_prompt`, `criteria_prompt`, `scoring_prompt`) using `str.format` placeholders. Module-level `_DEFAULT_*` constants hold the defaults.

#### `RaceEvaluator` error taxonomy

| Source | Error raised |
|---|---|
| Empty `task_prompt` / `target_report` / `reference_report` | `UserFixableError` |
| Judge returns non-JSON or fails Pydantic validation | `LLMRecoverableError` (after one internal retry) |
| Judge produces criteria with non-positive weight sum | `UserFixableError` |
| Weights below `_WEIGHT_RENORM_FLOOR` | `ValidationError` → surfaces as `UnexpectedError` at call site |
| Provider rate-limit / network | `TransientError` (bubbles from `ModelClient`) |

---

### `FactEvaluator` — `pyarnes_swarm.bench.fact`

> **Diagram:** [FACT pipeline](diagrams/07-fact-pipeline.html). Serial four-stage flow: extraction · dedup · per-claim verification · aggregate. Per-claim abstains when `sources[url]` is missing.

FACT (Factual Abundance and Citation Trustworthiness) evaluates whether citations in a long-form report actually support their attached claims. Two metrics:

- **Citation accuracy** = supported / (supported + unsupported) over the deduplicated claim list.
- **Effective citations** = absolute count of supported claims — rewards reports that cite more when cited well.

#### Types

```python
Sources = Mapping[str, str]  # url -> already-fetched content

class CitationClaim(BaseModel):
    statement: str         # non-empty
    url: str               # non-empty
    supported: bool | None
    reason: str

class FactMetrics(BaseModel):
    claims: tuple[CitationClaim, ...]
    total: int              # >= 0
    supported: int          # >= 0, <= total
    citation_accuracy: float  # in [0, 1]
    metadata: dict[str, Any]

    @model_validator(mode="after")
    def _validate_counts(self) -> Self: ...

    @computed_field
    @property
    def effective_citations(self) -> int:
        # Abundance metric — within one task it IS the supported count.
        return self.supported

    def to_eval_result(self, *, scenario: str, threshold: float = 0.8) -> EvalResult: ...
```

`FactPrompts` carries two overridable templates (`extraction_prompt`, `verification_prompt`) with placeholders `{report}`, `{statement}`, `{url}`, `{source}`.

#### `FactEvaluator`

```python
class FactEvaluator:
    def __init__(self, client: ModelClient, *, prompts: FactPrompts | None = None) -> None: ...

    async def evaluate(self, *, report: str, sources: Sources) -> FactMetrics: ...
```

Evaluation pipeline (serial — no concurrent judge calls):

1. **Extraction.** One judge call returns `{"claims": [{"statement", "url"}, ...]}`. Parsed into private `_ExtractedClaim` Pydantic instances.
2. **Dedup.** Exact `(statement, url)` pairs collapse; near-duplicate statements sharing the same URL collapse when `difflib.SequenceMatcher.ratio() >= 0.97` (stdlib; zero new dependency).
3. **Verification.** For each remaining pair in a plain `for` loop:
   - If `sources[url]` is absent → emit `CitationClaim(supported=None, reason="source_not_provided")`.
   - Else → one judge call with `{"supported": bool, "reason": str}`; emit `CitationClaim(supported=..., reason=...)`.
4. **Aggregate.** `total = count(supported is not None)`; `supported = count(supported is True)`; `citation_accuracy = supported / total` (0.0 if `total == 0`).

#### Helper

```python
def effective_citations_across(metrics: Iterable[FactMetrics]) -> float: ...
```

Free function (not a method) — matches the paper's definition of abundance as a cross-task mean.

#### `FactEvaluator` error taxonomy

| Source | Error raised |
|---|---|
| Empty `report` | `UserFixableError` |
| Extraction or verification judge returns bad JSON persistently (one retry) | `LLMRecoverableError` |
| `FactMetrics` constructed with inconsistent counts (`supported > total`, etc.) | `ValidationError` |
| Provider rate-limit / network | `TransientError` |

---

## Additional scorers

`ScorerVerdict` (older shape) is superseded by `ScoreResult` — use `ScoreResult` for all new scorers.

All scorers below implement the `Scorer` ABC (updated `score()` returns `ScoreResult`) and drop into existing `EvalSuite` flows.

### Algorithmic scorers (no LLM)

**`FuzzyScorer(threshold: float = 0.8)`** — uses `difflib.SequenceMatcher.ratio()` on stripped strings. Returns `ratio` as `ScoreResult.score`; sets `usage=None`.

**`RegexScorer(pattern: str, flags: int = 0)`** — compiles pattern once at init. `ScoreResult.score = 1.0` if `re.search` matches, else `0.0`; `usage=None`. Regex match group details are not surfaced in `EvalResult` — adopters who need them should subclass `RegexScorer` and emit a log entry via `pyarnes_swarm.observability.get_logger()`.

**`NumericToleranceScorer(tolerance: float, relative: bool = False)`** — parses `expected` and `actual` as floats; returns `ScoreResult(score=1.0)` if within tolerance (absolute by default, relative if flag set); raises `UserFixableError` on non-numeric input.

### LLM-as-judge scorer

**`LLMJudgeScorer(client: ModelClient, rubric: str)`** — overrides `score()` with an async judge call. `rubric` is a free-text prompt template with `{expected}`/`{actual}` placeholders. Returns structured JSON `{"score": float, "reason": str}` parsed from the model response. `ScoreResult.usage` carries the judge's token usage so it flows automatically into `EvalResult.usage` via `EvalSuite.run()`. Retries once on invalid JSON before raising `LLMRecoverableError`.

Three documented rubric strings (not exported constants — examples in the docstring, adopters own their prompts):

- `technical_accuracy` — `"Rate technical correctness 0–1..."`
- `constructiveness` — `"Rate how actionable the feedback is..."`
- `planning_rationality` — `"Given this plan and trace, rate..."`

`ModelClient` is imported from `pyarnes_swarm.agent`.

---

## Use-case reference: coding agents and deep agents

Taxonomy adopted from Agents-eval (qte77), which provides a three-tier taxonomy covering output quality and coordination quality. Every scorer below is defined in this spec or is explicitly flagged as adopter-owned.

> **Prerequisite specs:** The worked examples below reference `RunReport`, `EvalRunLogger`, and `TursoSink` (defined in `specs/consolidation/13-run-logger.md`) and `IterationBudget` plus token-accounting rules (defined across `04-swarm-api.md` and `12-token-budget.md`). Read those specs for the type definitions before implementing these patterns.

### Tier 1 — Algorithmic scorers (no LLM)

| Agents-eval metric | pyarnes scorer |
|----|---|
| `cosine_score` | `FuzzyScorer` (SequenceMatcher) |
| `jaccard_score` | `FuzzyScorer` (token-set variant) |
| `semantic_score` (BERTScore) | `FuzzyScorer` (adopter swaps in embeddings if desired — no dep added to pyarnes) |
| `execution_time` | `RunReport.wallclock_s` (see 13-run-logger.md) |
| `time_score` | adopter computes from `RunReport` (see 13-run-logger.md) |
| `task_success` | composed: `ExactMatchScorer` + adopter-owned `SubprocessScorer` |

### Tier 2 — LLM-as-judge scorers

| Agents-eval metric | pyarnes scorer |
|---|---|
| `technical_accuracy` | `LLMJudgeScorer(rubric="Rate technical correctness 0–1…")` |
| `constructiveness` | `LLMJudgeScorer(rubric="Rate how actionable the feedback is 0–1…")` |
| `planning_rationality` | `LLMJudgeScorer(rubric="Given this plan and trace, rate…")` |

Rubric strings are docstring examples, not module constants — adopters own their prompts.

### Tier 3 — Trajectory scorers (read the `ToolCallLogger` JSONL)

| Agents-eval metric | pyarnes scorer (adopter-owned) |
|---|---|
| `path_convergence` | `PathConvergenceScorer` |
| `tool_selection_accuracy` | `ToolSelectionAccuracyScorer` |
| `task_distribution_balance` | adopter-owned (multi-agent only) |
| `graph_complexity` | `GraphComplexityScorer` (optional, needs NetworkX — adopter adds dep) |

These consume the JSONL trace that `ToolCallLogger` writes to `.pyarnes/runs/<run_id>/tool_calls.jsonl`. No new capture layer required.

---

### Coding-agent use cases

#### UC-C1 — Patch correctness

- **What:** Did the agent produce a diff that applies cleanly and keeps tests green?
- **Primitives:** `ExactMatchScorer` on the post-patch file bytes (if the reference is a golden snapshot) **plus** an adopter-owned `SubprocessScorer` that shells out to `uv run tasks test` and returns pass-ratio as `ScoreResult.score`.
- **Signal:** `ScoreResult.score == 1.0` only if both match. Individual test failures are not enumerated in `EvalResult` — `score` reflects the LCS ratio; adopters needing failure lists should capture them in a custom `PostToolHook`.

#### UC-C2 — Edit minimality

- **What:** Did the agent touch only what was asked?
- **Primitives:** `NumericToleranceScorer` compares actual line-delta count against the expected envelope (tolerance 20 %). Compose with `RegexScorer(pattern=r"^(?!ALLOWED_PREFIX)")` run over the list of changed paths to reject out-of-scope edits.
- **Signal:** one composed verdict per scenario; failure surfaces any out-of-scope paths.

#### UC-C3 — Tool selection hygiene

- **What:** Did the agent prefer `Edit` over `Write` when the file existed? Did `Read` calls have `limit`/`offset`?
- **Primitives:** adopter-owned `ToolSelectionAccuracyScorer` that consumes `tool_calls.jsonl` and applies rules:
  - `Write` on an existing file → violation.
  - Unbounded `Read` on a file > 500 lines → violation.
  - `Grep` without `head_limit` → violation.
- **Signal:** Score = 1 − (violations / tool-call count). These rules mirror `CLAUDE.md` → `## Streaming / tool-output hygiene`.

#### UC-C4 — Planning rationality

- **What:** Given the plan and the executed trace, was the plan coherent with the actions?
- **Primitives:** `LLMJudgeScorer(rubric="Given this plan and trace, rate how coherent the plan is with the actions 0–1…")` fed the `RunReport` + the concatenated tool-call trace + the final diff. Returns `ScoreResult` with `score ∈ [0, 1]` and judge usage in `ScoreResult.usage`.
- **Signal:** `EvalResult.usage` captures judge cost for ops review.

---

### Deep-agent use cases

#### UC-D1 — Path convergence

- **What:** Of all tool calls made, how many were strictly needed?
- **Primitives:** `PathConvergenceScorer` computes `optimal_steps / actual_steps` from `tool_calls.jsonl`. `optimal_steps` comes from the scenario definition.
- **Signal:** 1.0 = perfect; <0.5 = significant wasted effort.

#### UC-D2 — Information coverage

- **What:** Did the agent retrieve every ground-truth fact?
- **Primitives:** adopter provides a `facts: list[str]` per scenario; per-fact `FuzzyScorer` with `threshold=0.85`; aggregate via `EvalSuite.run()`.
- **Signal:** Per-fact matrix + overall recall percentage.

#### UC-D3 — Hallucination / citation-groundedness

- **What:** Is every claim in the final answer traceable to a tool-returned source?
- **Primitives:** `LLMJudgeScorer` with a rubric that demands citation per claim. The judge sees the final answer + the `tool_calls.jsonl` contents of returned documents.
- **Signal:** Score = 1 − uncited/total. Judge reasoning enumerates uncited claims with line references.

#### UC-D4 — Budget discipline

- **What:** Did the run respect wallclock / token / retry caps?
- **Primitives:** an `IterationBudget` for shared step limits plus the token controls from `12-token-budget.md` wired through `LoopConfig`. Budget pressure surfaces as a clean stop or `UserFixableError` depending on the caller's policy.
- **Signal:** Surface `RunReport.wallclock_s`, `tokens_in + tokens_out`, `retries` in the evaluation row (see 13-run-logger.md). No new scorer needed — purely run-report analysis.

#### UC-D5 — Composition ablation (2³ matrix)

- **What:** Which subsystem contributes most to quality — guardrails? planning? retrieval?
- **Primitives:** run the same scenarios eight times with every combination of `{guardrails ∈ {on, off}} × {planner ∈ {on, off}} × {retrieval ∈ {subset_A, subset_B}}`. Each run gets its own `run_id`; `EvalRunLogger` (see 13-run-logger.md) writes one row per run into Turso (if configured) or per-run JSONL.
- **Signal:** Post-hoc SQL (against Turso) or a `tasks bench:report` markdown table shows per-composition mean score.

---

### Worked example — coding agent (UC-C1 + UC-C3)

```python
# tests/bench/test_coding_agent.py — adopter code, not pyarnes code
from pyarnes_swarm.bench import ExactMatchScorer, FuzzyScorer, EvalSuite
from pyarnes_swarm.capture import EvalRunLogger  # see 13-run-logger.md
from pyarnes_swarm.capture.sinks import TursoSink  # see 13-run-logger.md
from my_adopter_code.scorers import SubprocessScorer, ToolSelectionAccuracyScorer

suite = EvalSuite(name="coding-agent-eval")
sinks = [TursoSink(url=os.environ["TURSO_URL"],
                   auth_token=os.environ["TURSO_TOKEN"])]

async def run():
    logger = EvalRunLogger(run_dir=Path(".pyarnes/runs") / run_id,
                           sinks=sinks)
    for scenario in load_scenarios():
        result = await run_agent(scenario)
        results = [
            await suite.run(
                scenario.name, scenario.expected, result.diff,
                scorer=ExactMatchScorer(),
            ),
            await suite.run(
                scenario.name, None, result.workspace,
                scorer=SubprocessScorer(cmd=["uv", "run", "tasks", "test"]),
            ),
            await suite.run(
                scenario.name, scenario.allowed_tools, result.trace,
                scorer=ToolSelectionAccuracyScorer(),
            ),
        ]
    await logger.log_summary(suite, report=build_run_report())
```

No magic, no registry, everything explicit. Adopter owns `SubprocessScorer` and `ToolSelectionAccuracyScorer`.

### Worked example — deep agent (UC-D2 + UC-D4)

```python
from pyarnes_swarm import AgentRuntime
from pyarnes_swarm.agent import LoopConfig
from pyarnes_swarm.bench import FuzzyScorer, EvalSuite
from pyarnes_swarm.budget import IterationBudget

budget = IterationBudget(max_iterations=120)

async def run_scenario(scenario, runtime: AgentRuntime):
    runtime.config = LoopConfig(budget=budget)
    result = await runtime.run(
        [{"role": "user", "content": scenario.goal}]
    )
    answer = result[-1]["content"]
    suite = EvalSuite(name="deep-agent-eval")
    fact_results = [
        await suite.run(scenario.name, fact, answer, scorer=FuzzyScorer(threshold=0.85))
        for fact in scenario.facts
    ]
    coverage = sum(r.score for r in fact_results) / len(fact_results)
    return {"coverage": coverage}
```

`IterationBudget` caps shared loop steps; `FuzzyScorer` per-fact gives a coverage percentage; `RunReport` (spec 13) carries ops metrics to Turso for post-hoc dashboards.

---

### Provenance table — Agents-eval → pyarnes-bench

| Agents-eval (upstream) | pyarnes-bench |
|---|---|
| `Tier1Result.cosine_score` | `FuzzyScorer` (SequenceMatcher) |
| `Tier1Result.jaccard_score` | `FuzzyScorer` (token-set variant) |
| `Tier1Result.semantic_score` (BERT) | `FuzzyScorer` (adopter swaps implementation) |
| `Tier1Result.task_success` | composed: `ExactMatchScorer` + adopter `SubprocessScorer` |
| `Tier1Result.execution_time` | `RunReport.wallclock_s` (see 13-run-logger.md) |
| `Tier2Result.technical_accuracy` | `LLMJudgeScorer(rubric="Rate technical correctness 0–1…")` |
| `Tier2Result.constructiveness` | `LLMJudgeScorer(rubric="Rate how actionable the feedback is 0–1…")` |
| `Tier2Result.planning_rationality` | `LLMJudgeScorer(rubric="Given this plan and trace, rate…")` |
| `Tier3Result.path_convergence` | `PathConvergenceScorer` (adopter-owned) |
| `Tier3Result.tool_selection_accuracy` | `ToolSelectionAccuracyScorer` (adopter-owned) |
| `Tier3Result.coordination_centrality` | adopter-owned; multi-agent only |
| `Tier3Result.graph_complexity` | `GraphComplexityScorer` (optional, NetworkX) |
| `CompositeResult` | adopter-owned helper; pyarnes does **not** ship one |
| `TraceCollector → SQLite` (upstream) | `EvalRunLogger` + optional `TursoSink` (libSQL/async) (see 13-run-logger.md) |
| Streamlit GUI | out of scope |
| 2³ composition matrix | UC-D5 above — one `run_id` per cell |

### `LLMJudgeScorer` prompt examples

These are docstring examples in the scorer implementation — adopters copy and adapt them; they are not exported constants.

**`technical_accuracy` rubric:**

```
Rate technical correctness 0–1.
expected: {expected}
actual: {actual}
Reply with JSON: {"score": float, "reason": str}
```

**`constructiveness` rubric:**

```
Rate how actionable the feedback is 0–1.
expected: {expected}
actual: {actual}
Reply with JSON: {"score": float, "reason": str}
```

**`planning_rationality` rubric:**

```
Given this plan and trace, rate how coherent the plan is with the actions 0–1.
expected: {expected}
actual: {actual}
Reply with JSON: {"score": float, "reason": str}
```

## Exact Evaluation Formulas

To maintain strict parity across the evaluation dimensions, the axes must compute their scores using these non-negotiable formulas:

| Aspect | Metric / Heuristic Detail | Target Baseline | Implementation Source |
|---|---|---|---|
| **RACE** | $final\_score = \frac{S_{int}(target)}{S_{int}(target) + S_{int}(reference)}$ | Dynamically weighted over 4 dimensions, 3-trial averaging | `bench-race` spec |
| **FACT** | Near-duplicate dedup ratio | `difflib.ratio() >= 0.97` | `bench-fact` spec |
| **KPIs** | Token-reduction / speed floors | Minimum $5\times$ reduction | `PR-05` reporting |
| **Constraints**| Per-fixture weaker-repo penalty | $2\times$ threshold | `PR-05` accounting |

All failures/anomalies inside the frameworks categorize natively into the Error Taxonomy (e.g., `UserFixableError`, `LLMRecoverableError`).
