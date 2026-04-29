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

Audit subpackage (code-graph + audit, in-tree, LLM-free on the build path):

* **build_graph** / **save_graph** / **load_graph** — tree-sitter-python parser
  + JSON persistence.
* **audit_graph** / **Finding** — eight detectors (unused / cycles / duplicates /
  complexity / boundaries / flags).
* **god_nodes** / **surprising_connections** / **suggested_questions** —
  structural analyses.
* **AuditConfig** — `[tool.pyarnes-audit]` loader.

Names are exposed lazily via :pep:`562` ``__getattr__`` so importing
``pyarnes_bench.audit.*`` does not force the litellm/pydantic-heavy
evaluator stack into memory.
"""

from __future__ import annotations

from typing import Any

from pyarnes_core.packaging import version_of

__version__ = version_of("pyarnes-bench")

# Map of name → ``(submodule, attribute)``. Each pair is resolved lazily on
# first attribute access. Adopters keep `from pyarnes_bench import EvalSuite`
# working without paying the import cost on every audit-only CLI invocation.
_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    # Audit surface — networkx + tree-sitter only, no LLM deps.
    "AuditConfig": ("pyarnes_bench.audit", "AuditConfig"),
    "Finding": ("pyarnes_bench.audit", "Finding"),
    "audit_graph": ("pyarnes_bench.audit", "audit_graph"),
    "build_graph": ("pyarnes_bench.audit", "build_graph"),
    "god_nodes": ("pyarnes_bench.audit", "god_nodes"),
    "load_graph": ("pyarnes_bench.audit", "load_graph"),
    "save_graph": ("pyarnes_bench.audit", "save_graph"),
    "suggested_questions": ("pyarnes_bench.audit", "suggested_questions"),
    "surprising_connections": ("pyarnes_bench.audit", "surprising_connections"),
    # Burn — relatively light.
    "BurnTracker": ("pyarnes_bench.burn", "BurnTracker"),
    "ClaudeCodeProvider": ("pyarnes_bench.burn", "ClaudeCodeProvider"),
    "Cost": ("pyarnes_bench.burn", "Cost"),
    "CostCalculator": ("pyarnes_bench.burn", "CostCalculator"),
    "JsonlProvider": ("pyarnes_bench.burn", "JsonlProvider"),
    "LiteLLMCostCalculator": ("pyarnes_bench.burn", "LiteLLMCostCalculator"),
    "Provider": ("pyarnes_bench.burn", "Provider"),
    "SessionBurn": ("pyarnes_bench.burn", "SessionBurn"),
    "SessionMetadata": ("pyarnes_bench.burn", "SessionMetadata"),
    "TokenUsage": ("pyarnes_bench.burn", "TokenUsage"),
    # Eval / regression / scorers — pull pydantic/litellm transitively.
    "EvalResult": ("pyarnes_bench.eval", "EvalResult"),
    "EvalSuite": ("pyarnes_bench.eval", "EvalSuite"),
    "RegressionReport": ("pyarnes_bench.regression", "RegressionReport"),
    "AsyncScorer": ("pyarnes_bench.scorer", "AsyncScorer"),
    "CodeQualityScorer": ("pyarnes_bench.scorer", "CodeQualityScorer"),
    "ExactMatchScorer": ("pyarnes_bench.scorer", "ExactMatchScorer"),
    "LLMJudgeScorer": ("pyarnes_bench.scorer", "LLMJudgeScorer"),
    "Scorer": ("pyarnes_bench.scorer", "Scorer"),
    "GuardrailComplianceScorer": ("pyarnes_bench.scorers", "GuardrailComplianceScorer"),
    "ToolUseCorrectnessScorer": ("pyarnes_bench.scorers", "ToolUseCorrectnessScorer"),
    "TrajectoryLengthScorer": ("pyarnes_bench.scorers", "TrajectoryLengthScorer"),
    # Citation / report evaluators — heaviest, defer aggressively.
    "CitationClaim": ("pyarnes_bench.fact", "CitationClaim"),
    "FactEvaluator": ("pyarnes_bench.fact", "FactEvaluator"),
    "FactMetrics": ("pyarnes_bench.fact", "FactMetrics"),
    "FactPrompts": ("pyarnes_bench.fact", "FactPrompts"),
    "effective_citations_across": ("pyarnes_bench.fact", "effective_citations_across"),
    "RaceCriterion": ("pyarnes_bench.race", "RaceCriterion"),
    "RaceDimension": ("pyarnes_bench.race", "RaceDimension"),
    "RaceEvaluator": ("pyarnes_bench.race", "RaceEvaluator"),
    "RacePrompts": ("pyarnes_bench.race", "RacePrompts"),
    "RaceScore": ("pyarnes_bench.race", "RaceScore"),
    "RaceWeights": ("pyarnes_bench.race", "RaceWeights"),
    "SWEBenchScenario": ("pyarnes_bench.swe_bench", "SWEBenchScenario"),
}


import importlib  # noqa: E402  # below the lazy-loader table on purpose so cold-import paths stay minimal


def __getattr__(name: str) -> Any:
    """Resolve a public symbol lazily on first access."""
    try:
        module_path, attr = _LAZY_EXPORTS[name]
    except KeyError as exc:
        msg = f"module 'pyarnes_bench' has no attribute {name!r}"
        raise AttributeError(msg) from exc
    module = importlib.import_module(module_path)
    value = getattr(module, attr)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *_LAZY_EXPORTS})


__all__ = tuple(sorted(_LAZY_EXPORTS))
