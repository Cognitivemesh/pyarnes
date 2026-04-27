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

Token burn (lite port of getagentseal/codeburn):

* **TokenUsage** / **Cost** / **SessionBurn** — provider-agnostic data records.
* **Provider** / **JsonlProvider** — ABC hierarchy for session sources.
* **BurnTracker** — orchestrates providers; surfaces token cost as an eval axis.
* **CostCalculator** — protocol for pricing; **LiteLLMCostCalculator** default.
* **ClaudeCodeProvider** — reads ``~/.claude/projects/`` JSONL sessions (v1).
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
from pyarnes_bench.burn import (
    BurnTracker,
    ClaudeCodeProvider,
    Cost,
    CostCalculator,
    JsonlProvider,
    LiteLLMCostCalculator,
    Provider,
    SessionBurn,
    SessionMetadata,
    TokenUsage,
)
from pyarnes_bench.swe_bench import SWEBenchScenario

__all__ = [
    "AsyncScorer",
    "BurnTracker",
    "CitationClaim",
    "ClaudeCodeProvider",
    "CodeQualityScorer",
    "Cost",
    "CostCalculator",
    "EvalResult",
    "EvalSuite",
    "ExactMatchScorer",
    "FactEvaluator",
    "FactMetrics",
    "FactPrompts",
    "GuardrailComplianceScorer",
    "JsonlProvider",
    "LLMJudgeScorer",
    "LiteLLMCostCalculator",
    "Provider",
    "RaceCriterion",
    "RaceDimension",
    "RaceEvaluator",
    "RacePrompts",
    "RaceScore",
    "RaceWeights",
    "RegressionReport",
    "SWEBenchScenario",
    "Scorer",
    "SessionBurn",
    "SessionMetadata",
    "TokenUsage",
    "ToolUseCorrectnessScorer",
    "TrajectoryLengthScorer",
    "effective_citations_across",
]

from pyarnes_core.packaging import version_of

__version__ = version_of("pyarnes-bench")
