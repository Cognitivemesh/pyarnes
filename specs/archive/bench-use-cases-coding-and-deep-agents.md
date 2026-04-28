# bench-use-cases-coding-and-deep-agents

Use-case reference showing how the primitives from
`bench-scorer-verdict.md`, `harness-run-logger.md`, and
`harness-loop-budget-hooks.md` compose to evaluate two concrete
classes of agent: **coding agents** (edit / review / refactor) and
**deep agents** (multi-step, tool-heavy, long-horizon research).

Documentation-only spec. Ships no code.

## Context

`packages/bench/` today offers `ExactMatchScorer` and nothing else.
An adopter building a Claude-Code-style coding agent, or a deep
research agent with retrieval + planning loops, has no guidance on
which scorers to use, what to capture, or how to read the output.

Agents-eval (qte77) — the reference project analysed in the parent
review — provides a proven three-tier taxonomy (`Tier1Result`,
`Tier2Result`, `Tier3Result`; see its `docs/architecture.md`). Its
test tree also exercises eight agent compositions (the 2³ matrix of
researcher × analyst × synthesiser toggles), so there is real
evidence that this taxonomy covers both output quality and
coordination quality.

This document translates that taxonomy into pyarnes primitives,
respecting the **"adopter owns the scorers"** rule in
`docs/maintainer/packages/bench.md`. Every primitive referenced
below is already defined in the three sibling specs — this doc does
not introduce new ones.

## Goals / non-goals

**Goals.**

- One reference document listing **≥4 coding-agent use cases** and
  **≥5 deep-agent use cases**, each mapped to concrete pyarnes
  primitives.
- A provenance table showing which Agents-eval metric inspired each
  pyarnes scorer.
- Inline prompt examples for the three `LLMJudgeScorer` rubrics
  (short enough to copy, long enough to be useful).
- A worked example for each class of agent, showing how
  `EvalRunLogger`, `RunReport`, and the scorers fit together.

**Non-goals.**

- No new code, no new scorers beyond those specified in
  `bench-scorer-verdict.md`.
- No library-bundled fixtures. Adopters own their scenarios
  (rejected in Theme 6 of the plan — `packages/bench/fixtures/`
  would violate the "no magic" rule).
- No framework prescription. LangGraph / PydanticAI / bare `asyncio`
  are all fine — pyarnes stays framework-neutral.
- No GUI, no dashboard, no Streamlit port.

## Taxonomy adopted from Agents-eval

Three tiers, each satisfied by a set of pyarnes scorers. Every
scorer named here is defined in `bench-scorer-verdict.md` or arises
naturally from `harness-run-logger.md`.

### Tier 1 — Algorithmic scorers (no LLM)

| Agents-eval metric          | pyarnes scorer                    |
|-----------------------------|-----------------------------------|
| `cosine_score`              | `FuzzyScorer` (SequenceMatcher)   |
| `jaccard_score`             | `FuzzyScorer` (token-set variant) |
| `semantic_score` (BERTScore)| `FuzzyScorer` (adopter swaps in embeddings if desired — no dep added to pyarnes) |
| `execution_time`            | `RunReport.wallclock_s`           |
| `time_score`                | adopter computes from `RunReport` |
| `task_success`              | composed: `ExactMatchScorer` + adopter-owned `SubprocessScorer` |

### Tier 2 — LLM-as-judge scorers

| Agents-eval metric      | pyarnes scorer                                 |
|-------------------------|------------------------------------------------|
| `technical_accuracy`    | `LLMJudgeScorer(rubric=RUBRIC_TECHNICAL)`      |
| `constructiveness`      | `LLMJudgeScorer(rubric=RUBRIC_CONSTRUCTIVE)`   |
| `planning_rationality`  | `LLMJudgeScorer(rubric=RUBRIC_PLANNING)`       |

(Rubric strings are docstring examples, not module constants — see
the open question in `bench-scorer-verdict.md`.)

### Tier 3 — Trajectory scorers (read the `ToolCallLogger` JSONL)

| Agents-eval metric            | pyarnes scorer (adopter-owned)     |
|-------------------------------|------------------------------------|
| `path_convergence`            | `PathConvergenceScorer`            |
| `tool_selection_accuracy`     | `ToolSelectionAccuracyScorer`      |
| `task_distribution_balance`   | adopter-owned (multi-agent only)   |
| `graph_complexity`            | `GraphComplexityScorer` (optional, needs NetworkX — adopter adds dep) |

These consume the JSONL trace that `ToolCallLogger` already writes
to `.pyarnes/runs/<run_id>/tool_calls.jsonl`. No new capture layer
required.

## Coding-agent use cases

Each use case follows: **what to measure → which primitives →
acceptance signal**.

### UC-C1 — Patch correctness

- **What:** Did the agent produce a diff that applies cleanly and
  keeps tests green?
- **Primitives:** `ExactMatchScorer` on the post-patch file bytes
  (if the reference is a golden snapshot) **plus** an adopter-
  owned `SubprocessScorer` that shells out to `uv run tasks test`
  and returns pass-ratio as `ScorerVerdict.score`.
- **Signal:** `ScorerVerdict.score == 1.0` only if both match.
  Failure reasons carry the failing-test names in
  `ScorerVerdict.reason`.

### UC-C2 — Edit minimality

- **What:** Did the agent touch only what was asked?
- **Primitives:** `NumericToleranceScorer` compares actual line-
  delta count against the expected envelope (tolerance 20 %).
  Compose with `RegexScorer(pattern=r"^(?!ALLOWED_PREFIX)")` run
  over the list of changed paths to reject out-of-scope edits.
- **Signal:** one composed verdict per scenario; `reason`
  enumerates any out-of-scope paths.

### UC-C3 — Tool selection hygiene

- **What:** Did the agent prefer `Edit` over `Write` when the file
  existed? Did `Read` calls have `limit`/`offset`?
- **Primitives:** adopter-owned `ToolSelectionAccuracyScorer` that
  consumes `tool_calls.jsonl` and applies rules:
  - `Write` on an existing file → violation.
  - Unbounded `Read` on a file > 500 lines → violation.
  - `Grep` without `head_limit` → violation.
- **Signal:** Score = 1 − (violations / tool-call count).
  Mirrors Agents-eval `tool_selection_accuracy`.
- **Cross-reference:** these are the exact rules documented in
  `CLAUDE.md` → `## Streaming / tool-output hygiene`.

### UC-C4 — Planning rationality

- **What:** Given the plan and the executed trace, was the plan
  coherent with the actions?
- **Primitives:** `LLMJudgeScorer(rubric=RUBRIC_PLANNING)` fed the
  `RunReport` + the concatenated tool-call trace + the final diff.
  Returns `ScorerVerdict` with `score ∈ [0, 1]` and a `reason`
  that surfaces the judge's rationale.
- **Signal:** `ScorerVerdict.reason` is the review narrative;
  `ScorerVerdict.metadata['token_in' / 'token_out' / 'cost_usd']`
  captures judge cost for ops review.

## Deep-agent use cases

### UC-D1 — Path convergence

- **What:** Of all tool calls made, how many were strictly needed?
- **Primitives:** `PathConvergenceScorer` computes
  `optimal_steps / actual_steps` from `tool_calls.jsonl`.
  `optimal_steps` comes from the scenario definition.
- **Signal:** 1.0 = perfect; <0.5 = significant wasted effort.

### UC-D2 — Information coverage

- **What:** Did the agent retrieve every ground-truth fact?
- **Primitives:** adopter provides a `facts: list[str]` per
  scenario; per-fact `FuzzyScorer` with `threshold=0.85`; aggregate
  via `EvalSuite.run_async(..., concurrency=4)`.
- **Signal:** Per-fact matrix + overall recall percentage.

### UC-D3 — Hallucination / citation-groundedness

- **What:** Is every claim in the final answer traceable to a
  tool-returned source?
- **Primitives:** `LLMJudgeScorer` with a rubric that demands
  citation per claim. The judge sees the final answer + the
  `tool_calls.jsonl` contents of returned documents.
- **Signal:** `ScorerVerdict.reason` enumerates uncited claims
  with line references. `score = 1 − uncited/total`.

### UC-D4 — Budget discipline

- **What:** Did the run respect wallclock / token / retry caps?
- **Primitives:** `LoopBudget(max_wallclock_s=120, max_tokens=50_000,
  max_total_retries=5)` passed via `LoopConfig.budget`. The loop
  raises `UserFixableError("budget exceeded: <dim>")` on trip.
- **Signal:** Surface `RunReport.wallclock_s`, `tokens_in + tokens_out`,
  `retries` in the evaluation row. No new scorer needed — this is
  purely run-report analysis.

### UC-D5 — Composition ablation (2³ matrix, per Agents-eval)

- **What:** Which subsystem contributes most to quality —
  guardrails? planning? retrieval?
- **Primitives:** run the same scenarios eight times with every
  combination of `{guardrails ∈ {on, off}} × {planner ∈ {on, off}}
  × {retrieval ∈ {subset_A, subset_B}}`. Each run gets its own
  `run_id`; `EvalRunLogger` writes one row per run into Turso (if
  configured) or per-run JSONL.
- **Signal:** Post-hoc SQL (against Turso) or a `tasks bench:report`
  markdown table shows per-composition mean score. Directly
  mirrors Agents-eval's 8-composition study.

## Worked example — coding agent (UC-C1 + UC-C3 together)

```python
# tests/bench/test_coding_agent.py — adopter code, not pyarnes code
from pyarnes_bench import ExactMatchScorer, FuzzyScorer, EvalSuite
from pyarnes_harness.capture import EvalRunLogger
from pyarnes_harness.capture.sinks import TursoSink
from my_adopter_code.scorers import SubprocessScorer, ToolSelectionAccuracyScorer

suite = EvalSuite()
sinks = [TursoSink(url=os.environ["TURSO_URL"],
                   auth_token=os.environ["TURSO_TOKEN"])]

async def run():
    logger = EvalRunLogger(run_dir=Path(".pyarnes/runs") / run_id,
                           sinks=sinks)
    for scenario in load_scenarios():
        result = await run_agent(scenario)
        verdicts = [
            await ExactMatchScorer().verdict(scenario.expected, result.diff),
            await SubprocessScorer(cmd=["uv", "run", "tasks", "test"])
                .verdict(None, result.workspace),
            await ToolSelectionAccuracyScorer()
                .verdict(scenario.allowed_tools, result.trace),
        ]
        suite.add(scenario, verdicts)
    await logger.log_summary(suite, report=build_run_report())
```

No magic, no registry, everything explicit. Adopter owns
`SubprocessScorer` and `ToolSelectionAccuracyScorer`.

## Worked example — deep agent (UC-D2 + UC-D4 together)

```python
from pyarnes_bench import FuzzyScorer, LLMJudgeScorer, EvalSuite
from pyarnes_core.types import LoopBudget, ModelClient
from pyarnes_harness import LoopConfig, run_loop

budget = LoopBudget(max_wallclock_s=120, max_tokens=50_000,
                    max_total_retries=5)

async def run_scenario(scenario):
    cfg = LoopConfig(budget=budget, guardrails=my_chain)
    trace, answer, report = await run_loop(scenario.goal, cfg)
    fact_verdicts = await asyncio.gather(*[
        FuzzyScorer(threshold=0.85).verdict(fact, answer)
        for fact in scenario.facts
    ])
    coverage = sum(v.score for v in fact_verdicts) / len(fact_verdicts)
    return {"coverage": coverage, "report": report, "trace": trace}
```

The `LoopBudget` hook does the heavy lifting; `FuzzyScorer` per-fact
gives a coverage percentage; `RunReport` carries ops metrics to
Turso for post-hoc dashboards.

## Mapping table — Agents-eval → pyarnes-bench

| Agents-eval (upstream)                | pyarnes-bench (this repo)                                 |
|---------------------------------------|-----------------------------------------------------------|
| `Tier1Result.cosine_score`            | `FuzzyScorer` (spec: `bench-scorer-verdict.md`)           |
| `Tier1Result.jaccard_score`           | `FuzzyScorer` (token-set variant)                         |
| `Tier1Result.semantic_score` (BERT)   | `FuzzyScorer` (adopter swaps implementation)              |
| `Tier1Result.task_success`            | composed: `ExactMatchScorer` + adopter `SubprocessScorer` |
| `Tier1Result.execution_time`          | `RunReport.wallclock_s` (spec: `harness-run-logger.md`)   |
| `Tier2Result.technical_accuracy`      | `LLMJudgeScorer(rubric=RUBRIC_TECHNICAL)`                 |
| `Tier2Result.constructiveness`        | `LLMJudgeScorer(rubric=RUBRIC_CONSTRUCTIVE)`              |
| `Tier2Result.planning_rationality`    | `LLMJudgeScorer(rubric=RUBRIC_PLANNING)`                  |
| `Tier3Result.path_convergence`        | `PathConvergenceScorer` (adopter-owned)                   |
| `Tier3Result.tool_selection_accuracy` | `ToolSelectionAccuracyScorer` (adopter-owned)             |
| `Tier3Result.coordination_centrality` | adopter-owned; multi-agent only                           |
| `Tier3Result.graph_complexity`        | `GraphComplexityScorer` (optional, NetworkX)              |
| `CompositeResult`                     | adopter-owned helper; pyarnes does **not** ship one       |
| `TraceCollector → SQLite` (upstream)  | `EvalRunLogger` + optional `TursoSink` (libSQL/async)     |
| Streamlit GUI                         | **out of scope** per `CLAUDE.md`                          |
| 2³ composition matrix                 | UC-D5 above — one `run_id` per cell                       |

## Tests / acceptance (doc-only)

This is a documentation-only spec. Acceptance:

- Every scorer named here is defined in
  `bench-scorer-verdict.md` or `harness-run-logger.md` **or** is
  explicitly flagged as adopter-owned.
- No code example imports from `packages/bench/fixtures/` (the
  forbidden runtime path rejected in Theme 6 of the plan).
- No code example imports `sqlite3` — persistence stories route
  through `EvalRunLogger` / `TursoSink`.
- `uv run tasks md-lint` passes on this file.

## Open questions

- Should pyarnes ship `PathConvergenceScorer` and
  `ToolSelectionAccuracyScorer` in `pyarnes-bench`, given they
  depend only on the `ToolCallLogger` JSONL format (which is
  already part of the stable surface)? **Lean:** defer; keep them
  adopter-owned until at least two in-repo consumers exist, per
  `docs/maintainer/packages/bench.md` promotion criteria.
- Do we need a worked example showing the Turso post-hoc query for
  UC-D5? **Lean:** yes — add as a follow-up PR once the
  `TursoSink` schema is finalised in `harness-run-logger.md`.
