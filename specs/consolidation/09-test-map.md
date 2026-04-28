# pyarnes_swarm — Test Map

> **Spec header**
>
> | Field | Value |
> |---|---|
> | **Title** | pyarnes_swarm — Test Migration Map |
> | **Status** | active |
> | **Type** | testing |
> | **Owns** | mapping of legacy test files to new tests/swarm/ equivalents, migration rules (MIGRATE/DELETE/KEEP), test directory structure transitions |
> | **Depends on** | 08-test-strategy.md |
> | **Extends** | — |
> | **Supersedes** | — |
> | **Read after** | 08-test-strategy.md |
> | **Read before** | 15-tooling-artifacts.md |
> | **Not owned here** | TDD discipline (see `08-test-strategy.md`); dead-code audit (see `05-dead-code-audit.md`); tooling exclusions (see `15-tooling-artifacts.md`) |
> | **Last reviewed** | 2026-04-29 |

Maps every existing test file to its replacement in `tests/swarm/` or a deletion reason. Column definitions:

- **Old test** — path relative to `tests/`
- **New test** — path relative to `tests/swarm/`
- **Action** — MIGRATE (content port to new file), DELETE (redundant after new tests), KEEP (not covered by consolidation)

## Design Rationale

**Why migrate rather than rewrite from scratch?** Existing tests encode correct behaviour that was discovered through debugging and iteration — some of it non-obvious. A from-scratch rewrite risks losing that institutional knowledge. MIGRATE means port the intent, not necessarily the code. If the old test `assert loop.run(msgs) == expected` still tests the right thing, keep it. If it's testing an implementation detail that changed, rewrite it.

**Why are bench/, template/, and tasks/ tests kept and not migrated?** These packages are not being consolidated into `pyarnes_swarm`. They are separate concerns (`bench/` has its own optional extra, `template/` tests the Copier scaffold, `tasks/` tests the CLI runner). Migrating them would conflate consolidation with unrelated changes.

**Why DELETE `test_sandbox.py` rather than migrate it?** `SeccompSandbox` is being deleted entirely (Linux-only, zero callers). A test for deleted code has no migration target. Keeping it would either test nothing or test code that no longer exists.

## `tests/unit/` — flat files

| Old test | New test | Action |
|---|---|---|
| `test_agent_context.py` | `test_context.py` | MIGRATE — lifecycle FSM, AgentContext, Phase transitions |
| `test_atomic_write.py` | `test_context.py` (atomic_write tested via integration) | DELETE — low-value, stdlib wrapper |
| `test_benchmark_gate.py` | `test_guardrails.py` | MIGRATE — BenchmarkGateGuardrail threshold logic |
| `test_budget.py` | `test_budget.py` | MIGRATE — Budget immutability, consume(), allows() |
| `test_capture.py` | `test_agent.py` | MIGRATE — CapturedOutput, ToolCallLogger |
| `test_cc_session.py` | `test_agent.py` | MIGRATE — cc_session read/parse |
| `test_classifier.py` | `test_agent.py` | MIGRATE — ClassifiedError + classify_error() now inline in agent.py |
| `test_compaction.py` | `test_compaction.py` | MIGRATE — compact(), _find_cut_index(), cut-point pair safety |
| `test_compressor.py` | `test_compaction.py` | MIGRATE — capacity-threshold trigger (now MessageCompactor with context_window set) |
| `test_docs_examples.py` | DELETE | Docs are deleted; examples move to specs |
| `test_error_registry.py` | `test_errors.py` | MIGRATE — error taxonomy, hierarchy |
| `test_errors.py` | `test_errors.py` | MIGRATE — error types, str representation |
| `test_guardrails_catalog.py` | `test_guardrails.py` | MIGRATE — all guardrail check() behaviours |
| `test_guardrails.py` | `test_guardrails.py` | MIGRATE — GuardrailChain composition |
| `test_hardening.py` | `test_safety.py` | MIGRATE — hardening behaviours |
| `test_hooks.py` | `test_agent.py` | MIGRATE — PreToolHook, PostToolHook wiring |
| `test_injection.py` | `test_safety.py` | MIGRATE — injection detection |
| `test_integration.py` | `test_swarm.py` | MIGRATE — end-to-end loop integration |
| `test_iteration_budget.py` | `test_budget.py` | MIGRATE — IterationBudget async consume/refund |
| `test_lifecycle.py` | `test_context.py` | MIGRATE — Phase FSM transitions |
| `test_logger.py` | `test_observability.py` | MIGRATE — configure_logging, get_logger |
| `test_loop.py` | `test_agent.py` | MIGRATE — AgentLoop run(), error routing |
| `test_observer.py` | `test_observability.py` | MIGRATE — observer / event emission |
| `test_output_capture.py` | `test_agent.py` | MIGRATE — CapturedOutput |
| `test_post_scaffold.py` | KEEP (template/) | Template test, not part of consolidation |
| `test_redact.py` | `test_safety.py` | MIGRATE — credential redactor |
| `test_registry.py` | `test_tools.py` | MIGRATE — ToolRegistry register/dispatch |
| `test_repair.py` | `test_agent.py` | MIGRATE — JSON repair on tool-call args |
| `test_runtime.py` | `test_agent.py` | MIGRATE — AgentRuntime |
| `test_sandbox.py` | DELETE — `SeccompSandbox` is deleted | No replacement; SandboxHook Protocol stays in ports.py |
| `test_sanitize.py` | `test_safety.py` | MIGRATE — message sanitization pipeline |
| `test_semantic_guardrail.py` | `test_guardrails.py` | MIGRATE — SemanticGuardrail NaN-safe threshold |
| `test_session_id.py` | `test_agent.py` | MIGRATE — session ID generation (inlined) |
| `test_stable_surface.py` | DELETE — checks old monorepo public surface | New surface checked by `test_ports.py` |
| `test_steering.py` | `test_agent.py` | MIGRATE — SteeringQueue |
| `test_tasks_cli.py` | KEEP (tasks/) | Tasks package test |
| `test_tasks.py` | KEEP (tasks/) | Tasks package test |
| `test_telemetry.py` | `test_observability.py` | MIGRATE — configure_tracing, session_span |
| `test_tool_log.py` | `test_agent.py` | MIGRATE — ToolCallLogger |
| `test_transform.py` | `test_agent.py` | MIGRATE — TransformChain (now in agent.py) |
| `test_transport.py` | `test_providers.py` | MIGRATE — LiteLLM transport (now LiteLLMModelClient) |
| `test_validate_redirects.py` | DELETE — MkDocs redirect validation | Docs deleted |
| `test_verification.py` | `test_verification.py` | MIGRATE — VerificationLoop, VerificationResult |
| `test_violation_log.py` | `test_guardrails.py` | MIGRATE — violation logging |

## `tests/unit/dispatch/`

| Old test | New test | Action |
|---|---|---|
| `dispatch/test_action_kind.py` | `test_agent.py` | MIGRATE — ActionKind enum + classify() (inlined into agent.py) |
| `dispatch/test_retry_policy.py` | `test_agent.py` | MIGRATE — RetryPolicy + next_delay() (inlined) |

## `tests/unit/observability/`

| Old test | New test | Action |
|---|---|---|
| `observability/test_bound_logger.py` | `test_observability.py` | MIGRATE — log_event bind pattern |
| `observability/test_clock.py` | `test_observability.py` | MIGRATE — iso_now, monotonic_duration |
| `observability/test_events.py` | `test_observability.py` | MIGRATE — log_lifecycle_transition, log_tool_call |
| `observability/test_jsonable.py` | `test_observability.py` | MIGRATE — dumps, to_jsonable |

## `tests/unit/packaging/`

| Old test | New test | Action |
|---|---|---|
| `packaging/test_version.py` | DELETE — version_of() machinery deleted | `__version__ = "0.1.0"` requires no test |

## `tests/unit/safety/`

| Old test | New test | Action |
|---|---|---|
| `safety/test_arg_walker.py` | `test_safety.py` | MIGRATE — arg_walker |
| `safety/test_ast_deep.py` | `test_safety.py` | MIGRATE — deep AST analysis via libcst |
| `safety/test_command_scan.py` | `test_safety.py` | MIGRATE — command_scan blocklist |
| `safety/test_path_canon.py` | `test_safety.py` | MIGRATE — path canonicalization |
| `safety/test_path_parts.py` | `test_safety.py` | MIGRATE — path parts extraction |
| `safety/test_sandbox_check.py` | DELETE — SeccompSandbox deleted | `SandboxHook` Protocol has no implementation to test |
| `safety/test_semantic_judge.py` | `test_safety.py` | MIGRATE — semantic_judge NaN fix |

## `tests/unit/bench/`

| Old test | New test | Action |
|---|---|---|
| `bench/test_budget_hypothesis.py` | `test_budget.py` | MIGRATE — property-based Budget tests |
| `bench/test_burn.py` | KEEP (bench/) | BurnTracker, JsonlProvider — bench/ subpackage |
| `bench/test_citations.py` | KEEP (bench/) | Citation extraction |
| `bench/test_classify.py` | KEEP (bench/) | TaskKind classification |
| `bench/test_compare.py` | KEEP (bench/) | ModelComparison |
| `bench/test_dedupe.py` | KEEP (bench/) | Session deduplication |
| `bench/test_eval.py` | `test_bench_eval.py` | MIGRATE — EvalSuite (gains new run() tests) |
| `bench/test_fact.py` | KEEP (bench/) | FactEvaluator |
| `bench/test_judge.py` | KEEP (bench/) | Judge infrastructure |
| `bench/test_kpis.py` | KEEP (bench/) | SessionKpis |
| `bench/test_llm_judge.py` | KEEP (bench/) | LLMJudgeScorer |
| `bench/test_normalize.py` | KEEP (bench/) | Model alias normalisation |
| `bench/test_optimize.py` | KEEP (bench/) | all_detectors, HealthGrade |
| `bench/test_race.py` | KEEP (bench/) | RaceEvaluator |
| `bench/test_regression.py` | KEEP (bench/) | RegressionEvaluator |
| `bench/test_scorer.py` | `test_bench_scorers.py` | MIGRATE — **breaking change**: `Scorer.score()` now returns `ScoreResult`, not `float`; update all subclass assertions |
| `bench/test_scorers_catalog.py` | `test_bench_scorers.py` | MIGRATE — all scorer classes; assert `ScoreResult.score` not bare float |

## `tests/unit/tasks/`

| Old test | New test | Action |
|---|---|---|
| `tasks/test_bench_report.py` | KEEP (tasks/) | Tasks package |
| `tasks/test_bench_run.py` | KEEP (tasks/) | Tasks package |

## `tests/features/` (BDD)

| Old test | New test | Action |
|---|---|---|
| `features/steps/test_acceptance_steps.py` | `test_swarm.py` | MIGRATE — acceptance scenarios → integration tests |
| `features/steps/test_codeburn_steps.py` | KEEP (bench/) | codeburn BDD steps |
| `features/steps/test_fact_evaluation.py` | KEEP (bench/) | FACT BDD steps |
| `features/steps/test_feature_validation_steps.py` | DELETE — validates old features | Redundant once unit tests migrate |
| `features/steps/test_harness_steps.py` | `test_swarm.py` | MIGRATE — harness acceptance scenarios |
| `features/steps/test_race_evaluation.py` | KEEP (bench/) | RACE BDD steps |

## `tests/template/`

| Old test | New test | Action |
|---|---|---|
| `template/test_dev_hooks.py` | KEEP (template/) | Tests Copier template hooks |
| `template/test_scaffold.py` | KEEP (template/) | Tests Copier scaffold output |

## New test files with no old equivalent

These tests cover new surfaces that have no counterpart in the old test suite:

| New test | Covers |
|---|---|
| `test_providers.py` | `LiteLLMModelClient` (mocked LiteLLM), `ProviderConfig`, `SecretStore` resolution at first call; replaces and extends `test_transport.py` |
| `test_secrets.py` | `KeyringSecretStore` (mocked keyring), `EnvSecretStore`, `ChainedSecretStore` fallback ordering |
| `test_routing.py` | `RuleBasedRouter`, `LLMCostRouter` with mocked `litellm.model_cost`, `LLMCostRouter.observe()` |
| `test_bus.py` | `InMemoryBus` publish/subscribe, `TursoMessageBus` with `:memory:` db |
| `test_swarm.py` | `Swarm.run_agent()`, `Swarm.run_parallel()` result ordering, partial-failure isolation, timeout → `TimeoutError` |
| `test_ports.py` | All Protocol structural checks (ensure classes satisfy the Protocol without subclassing) |
| `test_token_budget.py` | `MessageCompactorConfig`, `MessageCompactor` trigger logic (mock `token_counter`), `overhead_tokens` baseline, `LLMCostRouter` context-window filter, `TaskMeta.required_context_tokens` |

## Summary

| Action | Count |
|---|---|
| MIGRATE to `tests/swarm/` | ~55 files |
| NEW (no old equivalent) | ~6 files |
| DELETE (dead tests) | ~10 files |
| KEEP (bench/, template/, tasks/) | ~25 files |

After Phase 2: old swarm-runtime tests under `tests/unit/` and `tests/features/` are deleted once migrated. `tests/swarm/`, `tests/template/`, bench-specific tests, and `tests/unit/tasks/` remain because those concerns are not fully absorbed into the core swarm migration.
