---
persona: maintainer
tags: [maintainer, packages, bench]
---

# pyarnes-bench

Lightweight evaluation and benchmarking toolkit. Score agent outputs, aggregate pass rates, plug in custom scorers. Depends only on `pyarnes-core` for logging.

## Module layout

Inter-package deps live in [Architecture § Package graph](../extend/architecture.md#package-graph). Internal layout:

```mermaid
graph TB
    Eval[eval.py<br/>EvalResult, EvalSuite]
    Scorer[scorer.py<br/>Scorer ABC<br/>ExactMatchScorer]
    Race[race.py<br/>RaceEvaluator<br/>RaceScore]
    Judge[_judge.py<br/>judge_json helper]
    Cits[_citations.py<br/>strip_markers]

    Eval --> Scorer
    Race --> Judge
    Race --> Cits
    Race --> Eval
```

| Module | Role |
|---|---|
| `eval.py` | `EvalResult` (immutable record) + `EvalSuite` (collects, runs, summarises batches). |
| `scorer.py` | `Scorer` ABC with `score(expected, actual) -> float` + `ExactMatchScorer` built-in. |
| `race.py` | `RaceEvaluator` (post-hoc LLM-as-judge, 4 dimensions, reference-normalized) + Pydantic result models (`RaceScore`, `RaceWeights`, `RaceCriterion`, `RacePrompts`, `RaceDimension`). |
| `_judge.py` | Private — `judge_json(client, prompt, PydanticModel)` helper with single retry + `LLMRecoverableError` on persistent failure. |
| `_citations.py` | Private — `strip_markers` + `URL_RE` utilities shared by report evaluators. |

## Why this package exists

Repo-wide rules live in [Architecture § Cross-cutting design principles](../extend/architecture.md#cross-cutting-design-principles). Package-specific reasons:

- **Adopter evaluation, not library benchmarks.** This package exists so adopters can measure whether their agent pipeline actually works — not for benchmarking pyarnes itself.
- **Scorer is pluggable.** Exact-match is the 80 % case; fuzzy scorers, LLM-judge scorers, and domain-specific scorers are all adopter responsibilities. The ABC keeps them swap-in.
- **Zero dep surface.** Only depends on `pyarnes-core`. No test framework, no HTTP, no reporters — stays a library, not a framework.

## Key flows

### Eval run

```mermaid
sequenceDiagram
    actor Adopter
    participant Suite as EvalSuite
    participant Scorer as Scorer.score
    participant Result as EvalResult

    Adopter->>Suite: EvalSuite(name="my-eval")
    loop for each scenario
        Adopter->>Scorer: score(expected, actual)
        Scorer-->>Adopter: float in [0, 1]
        Adopter->>Result: EvalResult(scenario, expected, actual, score, passed)
        Adopter->>Suite: suite.add(result)
    end
    Adopter->>Suite: suite.summary()
    Suite-->>Adopter: {"total", "passed", "failed", "pass_rate", "average_score"}
```

### Custom scorer authoring

```mermaid
sequenceDiagram
    actor Adopter
    participant MyScorer as FuzzyScorer<br/>(Scorer subclass)
    participant Suite as EvalSuite

    Adopter->>MyScorer: __init__(threshold=0.85)
    Adopter->>MyScorer: score("Hello, world", "hello world")
    MyScorer-->>Adopter: 0.93
    Adopter->>Suite: add(EvalResult(..., score=0.93, passed=(0.93 >= 0.85)))
```

The `Scorer` ABC doesn't dictate passing rules — the caller decides. Common pattern: a threshold kept on the scorer, a `passed=score >= threshold` check at record time.

## Public API

### EvalResult

Immutable record of a single evaluation. Fields:

| Field | Type | Description |
|---|---|---|
| `scenario` | `str` | Scenario identifier |
| `expected` | `Any` | Expected value |
| `actual` | `Any` | Actual value |
| `score` | `float` | Scorer output, typically in `[0, 1]` |
| `passed` | `bool` | Caller-defined pass/fail |

### EvalSuite

Collect and summarise `EvalResult` batches.

```python
from pyarnes_bench import EvalSuite, EvalResult

suite = EvalSuite(name="my-eval")
suite.add(EvalResult(scenario="greeting", expected="Hello", actual="hello", score=1.0, passed=True))
suite.summary()
# {"suite": "my-eval", "total": 1, "passed": 1, "failed": 0, "pass_rate": 1.0, "average_score": 1.0}
```

| Method | Description |
|---|---|
| `add(result)` | Append an `EvalResult` |
| `summary()` | Aggregate stats dict |
| `results` | Iterable of all stored results |

### Scorer ABC

```python
from pyarnes_bench import Scorer

class FuzzyScorer(Scorer):
    def score(self, expected, actual) -> float:
        ...
```

### ExactMatchScorer

```python
from pyarnes_bench import ExactMatchScorer

scorer = ExactMatchScorer(case_sensitive=False)
scorer.score("Hello", "hello")  # 1.0
scorer.score("Hello", "World")  # 0.0
```

| Field | Default | Description |
|---|---|---|
| `case_sensitive` | `True` | Comparison case-sensitivity |

### RaceEvaluator

Post-hoc LLM-as-judge for long-form reports. **Not a `Scorer` subclass** — it is a standalone async evaluator whose Pydantic result adapts to `EvalResult` via `.to_eval_result(...)`. Reason: `Scorer.score` is sync and returns a bare float; the RACE verdict shape (per-dimension weights, per-criterion scores, internal target/reference scores, final_score) is irreducibly richer and the judge call is async.

```python
from pyarnes_bench import RaceEvaluator

evaluator = RaceEvaluator(client=my_model_client, trials=3)
score = await evaluator.evaluate(
    task_prompt=task_description,
    target_report=target_text,
    reference_report=reference_text,
)
score.final_score                  # float in [0, 1]
score.to_eval_result(scenario="q1", threshold=0.5)  # -> EvalResult
```

| Constructor arg | Default | Description |
|---|---|---|
| `client` | required | Any `ModelClient` (structural Protocol) |
| `prompts` | `RacePrompts()` | Overridable prompt templates |
| `trials` | `3` | Weighting-judge trials to average |
| `dimensions` | all four | Subset of `RaceDimension` to score |

`RaceScore`, `RaceWeights`, `RaceCriterion`, `RacePrompts`, `RaceDimension` are Pydantic v2 `BaseModel`s (frozen, `extra="forbid"`). Invariants — weights sum ≈ 1, per-dimension criterion weights sum ≈ 1, scores ∈ [0, 1] — are enforced by `@model_validator`s at construction time.

### Future work

- `specs/claudecode-pyarnes-judge-plugin.md` — deferred design for a Claude Code plug-in that wraps `RaceEvaluator` (and `FactEvaluator`, once PR 2 lands) behind two skills and a `SubagentStop` hook. Status: not implemented; library surface is sufficient to build it.

## Extension points

- **Custom scorer:** subclass `Scorer`, implement `score(expected, actual) -> float`. That's it — no registration needed.
- **Composite scorer:** hold a list of `Scorer` instances, delegate, return max/mean — this lives in adopter code, not in pyarnes-bench.
- **Persistent results:** subclass `EvalSuite` to flush on `add()` or implement your own loader — keep the core `EvalSuite` in-memory only.

## Hazards / stable surface

- `EvalResult`, `EvalSuite`, `Scorer`, `ExactMatchScorer` (`pyarnes_bench`) — stable API, renames breaking.
- `EvalSuite.summary()` keys (`total`, `passed`, `failed`, `pass_rate`, `average_score`) — downstream scripts parse by name. Add keys freely; never rename or remove.
- The meta-use pattern (`tests/bench/test_agent_quality.py` in adopter projects) plugs domain scorers into `EvalSuite` — keep `add()` cheap and re-entrant.

## See also

- [Extension rules](../extend/rules.md) — custom scorer placement; no CLI here.
- [Architecture & meta-use](../extend/architecture.md) — how `EvalSuite` gates the coding agent in the dev-time harness.
- [pyarnes-core](core.md) — logger the suite writes transitions to.
