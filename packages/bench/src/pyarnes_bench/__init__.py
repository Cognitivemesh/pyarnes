"""pyarnes-bench — evaluation and benchmarking toolkit.

Provides primitives for defining, running, and scoring agent evaluations:

* **EvalResult** — immutable record of a single evaluation run.
* **EvalSuite** — collect, run, and summarise evaluation scenarios.
* **Scorer** — pluggable scoring protocol (exact match, fuzzy, LLM-as-judge).
"""

from __future__ import annotations

from pyarnes_bench.eval import EvalResult, EvalSuite
from pyarnes_bench.race import (
    RaceCriterion,
    RaceDimension,
    RaceEvaluator,
    RacePrompts,
    RaceScore,
    RaceWeights,
)
from pyarnes_bench.scorer import ExactMatchScorer, Scorer

__all__ = [
    "EvalResult",
    "EvalSuite",
    "ExactMatchScorer",
    "RaceCriterion",
    "RaceDimension",
    "RaceEvaluator",
    "RacePrompts",
    "RaceScore",
    "RaceWeights",
    "Scorer",
]

from pyarnes_core.packaging import version_of

__version__ = version_of("pyarnes-bench")
