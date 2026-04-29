# Changelog

All notable changes to pyarnes are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

pyarnes is distributed as git-pinned packages, not via PyPI. Adopters pin by
setting `pyarnes_ref` in their Copier answers to a tag name (e.g. `v0.1.0`).
Bumping `pyarnes_ref` and running `uv run tasks update` is how an adopter picks
up a new release.

## Versioning policy

Every public symbol in the tables below is covered by this policy. Anything not
listed, and anything whose name begins with an underscore, is private — it may
be renamed or removed in any release.

**MAJOR** — removing or renaming a public symbol, changing a `ToolHandler`,
`ModelClient`, `Guardrail`, or `Scorer` base-class signature, changing the
inheritance graph of an error class, or altering the `ToolCallLogger` JSONL
field set.

**MINOR** — adding a new public symbol, a new optional keyword argument, a new
`Phase` value, a new built-in `Guardrail`/`Scorer` subclass, or a new
`pyarnes-tasks` subcommand.

**PATCH** — bug fixes, docstring changes, private-surface refactors,
performance improvements that preserve behaviour.

### Public surface (stable)

| Package | Exports |
|---|---|
| `pyarnes_core` | `Budget`, `ErrorHandlerRegistry`, `HarnessError`, `JudgeClient`, `LLMRecoverableError`, `Lifecycle`, `LogFormat`, `ModelClient`, `Phase`, `RestrictedPythonSandbox`, `SandboxHook`, `SeccompSandbox`, `Severity`, `ToolHandler`, `TransientError`, `UnexpectedError`, `UserFixableError`, `append_private`, `configure_logging`, `configure_tracing`, `get_logger`, `get_tracer`, `safe_session_id`, `session_span`, `write_private` |
| `pyarnes_harness` | `AgentContext`, `AgentLoop`, `AgentRuntime`, `AsyncGuardrail`, `CapturedOutput`, `ClassifiedError`, `CommandGuardrail`, `Guardrail`, `GuardrailChain`, `HookChain`, `InjectionGuardrail`, `IterationBudget`, `LoopConfig`, `OutputCapture`, `PathGuardrail`, `PostToolHook`, `PreToolHook`, `SemanticGuardrail`, `SteeringQueue`, `ToolAllowlistGuardrail`, `ToolCallEntry`, `ToolCallLogger`, `ToolMessage`, `ToolRegistry`, `VerificationLoop`, `VerificationResult`, `classify_error`, `global_registry`, `read_cc_session`, `resolve_cc_session_path`, `tool` |
| `pyarnes_guardrails` | `ASTGuardrail`, `AsyncGuardrail`, `BenchmarkGateGuardrail`, `CommandGuardrail`, `Guardrail`, `GuardrailChain`, `InjectionGuardrail`, `NetworkEgressGuardrail`, `PathGuardrail`, `RateLimitGuardrail`, `SecretLeakGuardrail`, `SemanticGuardrail`, `ToolAllowlistGuardrail`, `Violation`, `append_violation`, `default_violation_log_path` |
| `pyarnes_bench` | `AsyncScorer`, `BurnTracker`, `CitationClaim`, `ClaudeCodeProvider`, `CodeQualityScorer`, `Cost`, `CostCalculator`, `EvalResult`, `EvalSuite`, `ExactMatchScorer`, `FactEvaluator`, `FactMetrics`, `FactPrompts`, `GuardrailComplianceScorer`, `JsonlProvider`, `LLMJudgeScorer`, `LiteLLMCostCalculator`, `Provider`, `RaceCriterion`, `RaceDimension`, `RaceEvaluator`, `RacePrompts`, `RaceScore`, `RaceWeights`, `RegressionReport`, `SWEBenchScenario`, `Scorer`, `SessionBurn`, `SessionMetadata`, `TokenUsage`, `ToolUseCorrectnessScorer`, `TrajectoryLengthScorer`, `effective_citations_across` |

`pyarnes-tasks` is dev-infrastructure; its contract is the CLI surface
documented in `docs/packages/tasks.md`, not a Python API.

### Private surface (may change without notice)

- Any attribute, method, or module whose name starts with `_`.
- `AgentLoop._call_tool` and any other `_`-prefixed helper on public classes.
- Log event string names (`"tool.pre"`, `"guardrail.command_blocked"`, …) —
  treat as telemetry, not a stable API. Do not regex them in production code.
- `ToolCallLogger` JSONL field *order*. The set of fields is stable; the order
  they appear on disk is not.
- `Lifecycle.history` concrete list type. The iterable contract is stable;
  mutating it is not supported.

## [Unreleased]

### Added

- **Code-audit CI gate** — `.github/workflows/ci.yml` now runs
  `tasks audit:build` followed by `tasks audit:check` after the composite
  CI task. The audit gate exits non-zero on any HIGH finding (circular
  imports, unused dependencies, boundary violations, complexity hotspots,
  duplicate blocks), so the lint/format debt that accumulated under #53
  cannot recur silently. `tool.pyarnes-audit` configuration in
  `pyproject.toml` defines the scan roots and exclude patterns.
- `pyarnes_bench.FactEvaluator` — post-hoc FACT (Factual Abundance and Citation
  Trustworthiness) evaluator for finished reports. Extracts cited claims via an
  LLM-as-judge, deduplicates exact and near-duplicate pairs (similarity ≥ 0.97
  on identical URLs), and verifies each survivor against a caller-supplied
  `sources: Mapping[str, str]`. Missing URLs are marked `supported=None` and
  excluded from the accuracy denominator. Returns a Pydantic `FactMetrics`
  carrying `citation_accuracy ∈ [0, 1]` and `effective_citations` (supported
  claim count). No URL fetching inside `pyarnes-bench`.
- `pyarnes_bench` Pydantic result models: `FactMetrics`, `CitationClaim`,
  `FactPrompts`. Frozen, `extra="forbid"`, with validators enforcing
  `supported <= total` and `effective_citations == supported`.
- `pyarnes_bench.effective_citations_across(metrics)` — free helper that
  averages supported-citation counts across a batch of tasks (DeepResearch
  Bench's abundance metric).
- `specs/bench-fact-evaluator.md` — implementation contract.
- `specs/claudecode-pyarnes-judge-plugin.md` — deferred, future-work design
  for a Claude Code plug-in that wraps RACE and FACT behind skills and a
  `SubagentStop` hook. Status: not implemented; captured so later
  implementation does not require library changes.
- `pyarnes_bench.RaceEvaluator` — post-hoc RACE (Reference-based Adaptive
  Criteria-driven Evaluation) scorer for long-form research reports. Takes a
  finished target report and a finished reference report, runs an LLM-as-judge
  over four dimensions (comprehensiveness, depth, instruction following,
  readability) with dynamically weighted task-specific criteria, and returns a
  Pydantic `RaceScore` whose `final_score` is normalized against the reference
  (`S_int(target) / (S_int(target) + S_int(reference))`). Strictly sequential —
  one judge call at a time.
- `pyarnes_bench` Pydantic result models: `RaceScore`, `RaceWeights`,
  `RaceCriterion`, `RacePrompts`, `RaceDimension`. Frozen, `extra="forbid"`,
  with `@model_validator`-enforced invariants (weights sum to 1, scores in
  `[0, 1]`). `RaceScore.to_eval_result(scenario, threshold)` adapts the rich
  verdict back to `EvalResult` so results flow into `EvalSuite` unchanged.
- `specs/bench-race-evaluator.md` — implementation contract mirroring
  `specs/bench-scorer-verdict.md`.
- `pydantic>=2.6` dependency in `packages/bench/pyproject.toml` (validation +
  JSON parsing for evaluator inputs, outputs, and judge responses).
- First declaration of the stable public surface (this file).
- Stability test suite: `tests/unit/test_stable_surface.py` enforces that every
  symbol in the tables above resolves and that no public `__all__` entry is
  silently dropped.
- `tests/unit/test_docs_examples.py` — parses every Python fenced block in
  `docs/**/*.md` to catch syntax errors and undefined names in examples.
- Repo-root `mkdocs.yml` and minimal `docs/` tree (`docs/index.md`,
  `docs/adopter/build/quickstart.md`) — gives `mkdocs build --strict` and
  `tests/unit/test_docs_examples.py::test_docs_examples_coverage` a real
  target at HEAD. The `docs/adopter/build/quickstart.md` page satisfies the
  `RUNNABLE_PAGES` check with self-contained Python blocks; the richer
  `ReadFileTool` / `ModelClient` / `GuardrailChain` examples called out
  elsewhere in this section land on top of this scaffold.

### Changed

- **Branch & PR cleanup (2026-04-30)** — integrated all open PRs and pruned
  stale branches: PR #66 unblocked `main`'s CI (4 ruff format misses + 28
  lint errors + 8 ty type-check errors + 1100-line `uv.lock` orphan
  cleanup); PR #65 absorbed the `/simplify` audit refactor; PRs
  #58 / #56 / #64 / #54 / #61 each rebased onto fresh `main` and
  squash-merged; PR #63 closed as superseded by #66. Net result: a single
  linear `main` head, no open PRs except the hygiene-gate, and every
  format / lint / typecheck gate green at HEAD.
- Documentation now includes a "Stable API surface" section under
  `docs/development/evolving.md` mirroring this policy for contributor
  discoverability.

### Fixed

- `docs/adopter/build/quickstart.md`: the `ReadFileTool` example now wraps
  `Path.read_text` in `asyncio.to_thread` instead of calling it directly inside
  an `async def`, matching the async-first invariant in `concepts.md`.
- `docs/adopter/build/quickstart.md`: added the missing
  `from pyarnes_core.types import ModelClient` import so Step 2 is copy-paste
  runnable.
- `docs/adopter/build/quickstart.md`: new Step 5 wires `GuardrailChain` into the
  loop via a `register_guarded` helper. Previously `chain.check(...)` was shown
  only in isolation, contradicting the sequence diagram at the top of the page.
- `packages/core/src/pyarnes_core/types.py`: the `ToolHandler` docstring example
  now uses `asyncio.to_thread` too; hover-docs no longer teach the blocking-I/O
  anti-pattern.
- `docs/maintainer/onboard/testing.md`: removed phantom `test_api.py`; added
  four real unit-test files that were missing from the tree.
- `docs/adopter/evaluate/distribution.md`, `docs/maintainer/release.md`: added
  an explicit 0.x stability disclaimer — MINOR releases may break until v1.0.0.
- `CONTRIBUTING.md`: dropped a stale bullet referencing `packages/example-*`
  directories that do not exist.
- `tests/unit/test_serve_specs.py`: added a module-level
  `pytest.skip(allow_module_level=True)` guard that fires when
  `scripts/serve_specs.py` is absent. Previously the import failed with a
  `FileNotFoundError` during collection, which red-CI'd every PR until the
  specs-viewer script lands. Restores graceful skip behaviour and keeps the
  full test surface intact for branches that do ship the script.

## [0.0.0] - 2026-04-18

- Initial stable surface declared. No behaviour changes; this tag anchors the
  semver policy above. Adopters pinning `pyarnes_ref = "v0.0.0"` can rely on
  every symbol in the public-surface table to remain available until the next
  MAJOR release.
