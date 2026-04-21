---
persona: adopter
tags: [adopter, build, bench, evaluation]
---

# Benchmarking your agent

`pyarnes-bench` gives you a lightweight evaluation framework that fits inside
your existing test suite. No external services, no separate eval runner — just
Python objects you compose like any other harness component.

## What pyarnes-bench provides

| Symbol | Role |
|---|---|
| `EvalResult` | Immutable record of one evaluation run (scenario, expected, actual, score, passed) |
| `EvalSuite` | Collects results, computes pass-rate and average score |
| `Scorer` | Abstract base — implement `score(expected, actual) → float` |
| `ExactMatchScorer` | Built-in scorer: 1.0 on exact match, 0.0 otherwise |

All four symbols are importable from `pyarnes_bench`:

```python
from pyarnes_bench import EvalResult, EvalSuite, ExactMatchScorer, Scorer
```

## Quick start: exact-match suite

```python
import asyncio
from pyarnes_bench import EvalResult, EvalSuite, ExactMatchScorer

scorer = ExactMatchScorer()
suite = EvalSuite(name="greeting-agent")

scenarios = [
    ("says hello", "Hello!", "Hello!"),
    ("says goodbye", "Goodbye!", "See ya"),
]

for name, expected, actual in scenarios:
    score = scorer.score(expected, actual)
    suite.add(EvalResult(
        scenario=name,
        expected=expected,
        actual=actual,
        score=score,
        passed=score >= 1.0,
    ))

print(suite.summary())
# {'suite': 'greeting-agent', 'total': 2, 'passed': 1, 'failed': 1,
#  'pass_rate': 0.5, 'average_score': 0.5}
```

## Running evaluations in pytest

Add an `eval` mark so your suite can run separately from unit tests:

```python
import pytest
from pyarnes_bench import EvalSuite, ExactMatchScorer, EvalResult

@pytest.mark.eval
async def test_agent_greets_user(loop_fixture) -> None:
    suite = EvalSuite(name="greet")
    scorer = ExactMatchScorer(case_sensitive=False)

    messages = await loop_fixture.run([
        {"role": "user", "content": "Say hello."}
    ])
    actual = messages[-1]["content"]

    result = EvalResult(
        scenario="greet",
        expected="hello",
        actual=actual.lower(),
        score=scorer.score("hello", actual.lower()),
        passed=scorer.score("hello", actual.lower()) >= 1.0,
    )
    suite.add(result)
    assert suite.pass_rate == 1.0, suite.summary()
```

Run only eval tests:

```bash
uv run pytest -m eval
```

## Writing a custom scorer

Implement the `Scorer` ABC to add fuzzy matching, regex checks, or LLM-as-judge:

```python
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from pyarnes_bench import Scorer


@dataclass(frozen=True, slots=True)
class FuzzyScorer(Scorer):
    """Score based on longest-common-subsequence similarity."""

    threshold: float = 0.8

    def score(
        self,
        expected: Any,
        actual: Any,
        *,
        scenario: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> float:
        ratio = SequenceMatcher(None, str(expected), str(actual)).ratio()
        return ratio
```

Use `metadata` to pass rubric weights or per-scenario instructions to an
LLM-as-judge scorer without touching the method signature.

## Logging results to JSONL

`EvalResult.as_dict()` returns a plain dict. Pipe it through loguru's
structured logger so results land in your `.jsonl` log file:

```python
from pyarnes_core.observe import get_logger

logger = get_logger(__name__)

for result in suite.results:
    logger.bind(**result.as_dict()).info("eval.result")
```

Each log line will be a valid JSON object:

```json
{"event": "eval.result", "scenario": "greet", "expected": "Hello!", "actual": "Hello!", "score": 1.0, "passed": true, ...}
```

## Interpreting the summary

`suite.summary()` returns:

| Key | Meaning |
|---|---|
| `total` | Number of scenarios run |
| `passed` | Scenarios with `passed=True` |
| `failed` | `total - passed` |
| `pass_rate` | `passed / total` (0.0–1.0) |
| `average_score` | Mean of all `score` values |

A `pass_rate` of 1.0 means every scenario passed. Use `average_score` to
track continuous improvement even when pass/fail thresholds are binary.

## See also

- [pyarnes-bench package deep dive](../../maintainer/packages/bench.md) — internals, scorer protocol, extension points.
- [Quick start](quickstart.md) — wire `EvalSuite` into an agent loop.
- [Task runner](tasks.md) — add a custom `bench` task to run evaluations.
