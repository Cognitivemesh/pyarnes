"""pyarnes-burn — token cost tracking + CodeBurn-style observability.

Reads provider session files (v1: JSONL only) and surfaces token
consumption, KPIs and waste-detection findings as evaluation axes
inside ``pyarnes-bench``. Lite port of ``getagentseal/codeburn``,
scoped to evaluation use-cases.

Excluded intentionally: dashboard UI, FX conversion, yield (git
correlation) analysis. These belong in a full codeburn integration,
not an evaluation sub-library.

Three layers:

* **Visibility** — :class:`SessionBurn`, :class:`BurnTracker`,
  :class:`LiteLLMCostCalculator`.
* **Measurement** — :class:`SessionKpis` (one-shot rate, retry loops,
  cache hit rate) plus :class:`ModelComparison` for A/B model studies.
* **Optimization** — :class:`OptimizeReport` with seven detectors and
  an A-F :class:`HealthGrade`.

Extension point: subclass :class:`JsonlProvider` (six hooks) to add any
JSONL-based tool; subclass :class:`Provider` directly for SQL/binary
formats.
"""

from __future__ import annotations

from pyarnes_bench.burn.classify import TaskKind, classify, classify_window
from pyarnes_bench.burn.claude_code import ClaudeCodeProvider, parse_session_calls
from pyarnes_bench.burn.compare import ModelComparison, ModelStats, compare_models
from pyarnes_bench.burn.costing import CostCalculator, LiteLLMCostCalculator
from pyarnes_bench.burn.dedupe import dedupe
from pyarnes_bench.burn.kpis import (
    ProjectKpis,
    SessionKpis,
    compute_project_kpis,
    compute_session_kpis,
)
from pyarnes_bench.burn.normalize import (
    CANONICAL_TOOLS,
    MODEL_ALIASES,
    ModelAlias,
    normalize_tool,
    resolve_model,
)
from pyarnes_bench.burn.optimize import (
    Finding,
    HealthGrade,
    OptimizeReport,
    SessionInput,
    all_detectors,
    compute_grade,
    load_previous_report,
    save_report,
    snapshot_dir,
)
from pyarnes_bench.burn.optimize import (
    run as run_optimize,
)
from pyarnes_bench.burn.provider import BurnTracker, JsonlProvider, Provider
from pyarnes_bench.burn.types import Cost, SessionBurn, SessionMetadata, TokenUsage

__all__ = [
    "CANONICAL_TOOLS",
    "MODEL_ALIASES",
    "BurnTracker",
    "ClaudeCodeProvider",
    "Cost",
    "CostCalculator",
    "Finding",
    "HealthGrade",
    "JsonlProvider",
    "LiteLLMCostCalculator",
    "ModelAlias",
    "ModelComparison",
    "ModelStats",
    "OptimizeReport",
    "ProjectKpis",
    "Provider",
    "SessionBurn",
    "SessionInput",
    "SessionKpis",
    "SessionMetadata",
    "TaskKind",
    "TokenUsage",
    "all_detectors",
    "classify",
    "classify_window",
    "compare_models",
    "compute_grade",
    "compute_project_kpis",
    "compute_session_kpis",
    "dedupe",
    "load_previous_report",
    "normalize_tool",
    "parse_session_calls",
    "resolve_model",
    "run_optimize",
    "save_report",
    "snapshot_dir",
]
