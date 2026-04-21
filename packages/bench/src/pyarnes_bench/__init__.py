"""pyarnes-bench — evaluation and benchmarking toolkit.

Provides primitives for defining, running, and scoring agent evaluations:

* **EvalResult** — immutable record of a single evaluation run.
* **EvalSuite** — collect, run, and summarise evaluation scenarios.
* **Scorer** — pluggable scoring protocol (exact match, fuzzy, LLM-as-judge).
* **LLMJudgeScorer** — LLM-as-judge scorer for open-ended evaluation.
* **CodeQualityScorer** — multi-dimension code quality scorer.
* **RegressionReport** — cross-version pass-rate comparison.
* **SWEBenchScenario** — SWE-bench instance data record.
* **RaceEvaluator** — reference-based long-form report evaluation (4 dimensions, LLM-as-judge).
* **FactEvaluator** — citation trustworthiness evaluation against adopter-supplied sources.

Trajectory scorers (consume ``ToolCallEntry`` iterables from either the
in-process loop or a Claude Code transcript):

* **ToolUseCorrectnessScorer** — LCS against a reference tool sequence.
* **TrajectoryLengthScorer** — penalise runs that over/undershoot.
* **GuardrailComplianceScorer** — ratio of clean calls to sidecar violations.
"""

from __future__ import annotations

from pyarnes_bench.eval import EvalResult, EvalSuite
from pyarnes_bench.fact import (
    CitationClaim,
    FactEvaluator,
    FactMetrics,
    FactPrompts,
    effective_citations_across,
)
from pyarnes_bench.race import (
    RaceCriterion,
    RaceDimension,
    RaceEvaluator,
    RacePrompts,
    RaceScore,
    RaceWeights,
)
from pyarnes_bench.regression import RegressionReport
from pyarnes_bench.scorer import (
    AsyncScorer,
    CodeQualityScorer,
    ExactMatchScorer,
    LLMJudgeScorer,
    Scorer,
)
from pyarnes_bench.scorers import (
    GuardrailComplianceScorer,
    ToolUseCorrectnessScorer,
    TrajectoryLengthScorer,
)
from pyarnes_bench.swe_bench import SWEBenchScenario

__all__ = [
    "AsyncScorer",
    "CitationClaim",
    "CodeQualityScorer",
    "EvalResult",
    "EvalSuite",
    "ExactMatchScorer",
    "FactEvaluator",
    "FactMetrics",
    "FactPrompts",
    "GuardrailComplianceScorer",
    "LLMJudgeScorer",
    "RaceCriterion",
    "RaceDimension",
    "RaceEvaluator",
    "RacePrompts",
    "RaceScore",
    "RaceWeights",
    "RegressionReport",
    "SWEBenchScenario",
    "Scorer",
    "ToolUseCorrectnessScorer",
    "TrajectoryLengthScorer",
    "effective_citations_across",
]

from pyarnes_core.packaging import version_of

__version__ = version_of("pyarnes-bench")
