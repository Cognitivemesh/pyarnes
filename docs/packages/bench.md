# pyarnes-bench

Evaluation and benchmarking toolkit for scoring agent outputs.

## What it provides

| Class | Purpose |
|---|---|
| `EvalResult` | Immutable record of a single evaluation (scenario, expected, actual, score, passed) |
| `EvalSuite` | Collect, run, and summarise batches of evaluations |
| `Scorer` | Abstract base class — implement `score(expected, actual) -> float` |
| `ExactMatchScorer` | Built-in scorer: 1.0 if equal, 0.0 otherwise (optional case-insensitive) |

## Usage

```python
from pyarnes_bench import EvalResult, EvalSuite, ExactMatchScorer

scorer = ExactMatchScorer(case_sensitive=False)
suite = EvalSuite(name="my-eval")

score = scorer.score("Hello", "hello")  # 1.0 (case-insensitive)
suite.add(EvalResult(scenario="greeting", expected="Hello", actual="hello", score=score, passed=True))

print(suite.summary())
# {"suite": "my-eval", "total": 1, "passed": 1, "failed": 0, "pass_rate": 1.0, "average_score": 1.0}
```

## Writing custom scorers

```python
from pyarnes_bench import Scorer

class FuzzyScorer(Scorer):
    def score(self, expected, actual) -> float:
        # Your fuzzy matching logic here
        ...
```

## Dependencies

- `pyarnes-core` — logging

