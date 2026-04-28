"""Enforce the stable public API surface declared in ``CHANGELOG.md``.

Adopters pin pyarnes by git ref and rely on the symbols listed below to remain
importable. A contributor who deletes or renames a symbol should see this test
fail *before* the change reaches a release tag. If an intentional breaking
change lands, update both this file and ``CHANGELOG.md``.
"""

from __future__ import annotations

import importlib
from types import ModuleType

import pytest

STABLE_SURFACE: dict[str, frozenset[str]] = {
    "pyarnes_core": frozenset(
        {
            "Budget",
            "ErrorHandlerRegistry",
            "HarnessError",
            "JudgeClient",
            "LLMRecoverableError",
            "Lifecycle",
            "LogFormat",
            "ModelClient",
            "Phase",
            "RestrictedPythonSandbox",
            "SandboxHook",
            "SeccompSandbox",
            "Severity",
            "ToolHandler",
            "TransientError",
            "UnexpectedError",
            "UserFixableError",
            "append_private",
            "configure_logging",
            "configure_tracing",
            "get_logger",
            "get_tracer",
            "safe_session_id",
            "session_span",
            "write_private",
        }
    ),
    "pyarnes_harness": frozenset(
        {
            "AgentContext",
            "AgentLoop",
            "AgentRuntime",
            "AsyncGuardrail",
            "CapturedOutput",
            "ClassifiedError",
            "CommandGuardrail",
            "CompactionConfig",
            "CompactionTransformer",
            "ContextCompressor",
            "Guardrail",
            "GuardrailChain",
            "HookChain",
            "InjectionGuardrail",
            "IterationBudget",
            "LoopConfig",
            "MessageTransformer",
            "OutputCapture",
            "PathGuardrail",
            "PostToolHook",
            "PreToolHook",
            "SemanticGuardrail",
            "SteeringQueue",
            "ToolAllowlistGuardrail",
            "ToolCallEntry",
            "ToolCallLogger",
            "ToolMessage",
            "ToolRegistry",
            "TransformChain",
            "VerificationLoop",
            "VerificationResult",
            "classify_error",
            "compact",
            "global_registry",
            "read_cc_session",
            "resolve_cc_session_path",
            "tool",
        }
    ),
    "pyarnes_guardrails": frozenset(
        {
            "ASTGuardrail",
            "AsyncGuardrail",
            "BenchmarkGateGuardrail",
            "CommandGuardrail",
            "Guardrail",
            "GuardrailChain",
            "InjectionGuardrail",
            "NetworkEgressGuardrail",
            "PathGuardrail",
            "RateLimitGuardrail",
            "SecretLeakGuardrail",
            "SemanticGuardrail",
            "ToolAllowlistGuardrail",
            "Violation",
            "append_violation",
            "default_violation_log_path",
        }
    ),
    "pyarnes_bench": frozenset(
        {
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
        }
    ),
}


@pytest.fixture(scope="module", params=sorted(STABLE_SURFACE.keys()))
def module(request: pytest.FixtureRequest) -> ModuleType:
    return importlib.import_module(request.param)


def test_all_declared(module: ModuleType) -> None:
    """Every package declares ``__all__``."""
    assert hasattr(module, "__all__"), f"{module.__name__} must declare __all__"
    assert isinstance(module.__all__, list)


def test_stable_symbols_exported(module: ModuleType) -> None:
    """Every symbol in the stable surface appears in ``__all__``."""
    expected = STABLE_SURFACE[module.__name__]
    actual = set(module.__all__)
    missing = expected - actual
    assert not missing, (
        f"{module.__name__} is missing stable exports: {sorted(missing)}. "
        "Removing a public symbol is a MAJOR version change — see CHANGELOG.md."
    )


def test_stable_symbols_resolve(module: ModuleType) -> None:
    """Every stable symbol actually resolves from the package."""
    for name in STABLE_SURFACE[module.__name__]:
        assert hasattr(module, name), (
            f"{module.__name__}.{name} is in the stable surface but does not resolve. Breaking change?"
        )


def test_no_private_symbols_in_all(module: ModuleType) -> None:
    """``__all__`` never exposes underscore-prefixed names."""
    leaked = [n for n in module.__all__ if n.startswith("_")]
    assert not leaked, f"{module.__name__}.__all__ leaks private names: {leaked}"


def test_star_import_matches_all(module: ModuleType) -> None:
    """``from pkg import *`` yields exactly ``__all__``."""
    namespace: dict[str, object] = {}
    exec(f"from {module.__name__} import *", namespace)  # noqa: S102
    imported = {k for k in namespace if not k.startswith("_")}
    declared = set(module.__all__)
    assert imported == declared, (
        f"Star-import of {module.__name__} yields {sorted(imported)} but __all__ is {sorted(declared)}"
    )
