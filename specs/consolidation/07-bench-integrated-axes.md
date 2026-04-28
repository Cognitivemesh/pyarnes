# pyarnes_swarm — Bench: Integrated Evaluation Axes

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

These remain post-hoc, sequential evaluators. No change to their `score()` / `to_eval_result()` API. They now return `ScoreResult` from their underlying `Scorer` implementations, so their token usage from the LLM judge call flows automatically into `EvalResult.usage` via `EvalSuite.run()`.

See `specs/bench-race-evaluator.md` (archived) and `specs/bench-fact-evaluator.md` (archived) for the evaluator implementations — no changes needed; only the scorer protocol changes.
