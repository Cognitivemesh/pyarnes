"""pyarnes-bench — evaluation and benchmarking toolkit.

Provides primitives for defining, running, and scoring agent evaluations:

* **EvalResult** — immutable record of a single evaluation run.
* **EvalSuite** — collect, run, and summarise evaluation scenarios.
* **Scorer** — pluggable scoring protocol (exact match, fuzzy, LLM-as-judge).
* **LLMJudgeScorer** — LLM-as-judge scorer for open-ended evaluation.
* **CodeQualityScorer** — multi-dimension code quality scorer.
* **RegressionReport** — cross-version pass-rate comparison.
* **SWEBenchScenario** — SWE-bench instance data record.
"""

from __future__ import annotations

from pyarnes_bench.eval import EvalResult, EvalSuite
from pyarnes_bench.regression import RegressionReport
from pyarnes_bench.scorer import (
    AsyncScorer,
    CodeQualityScorer,
    ExactMatchScorer,
    LLMJudgeScorer,
    Scorer,
)
from pyarnes_bench.swe_bench import SWEBenchScenario

__all__ = [
    "AsyncScorer",
    "CodeQualityScorer",
    "EvalResult",
    "EvalSuite",
    "ExactMatchScorer",
    "LLMJudgeScorer",
    "RegressionReport",
    "SWEBenchScenario",
    "Scorer",
]

from pyarnes_core.packaging import version_of

__version__ = version_of("pyarnes-bench")
