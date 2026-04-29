# pyarnes_swarm — Consolidation Overview

> **Spec header**
>
> | Field | Value |
> |---|---|
> | **Title** | pyarnes_swarm — Consolidation Overview |
> | **Status** | active |
> | **Type** | core-runtime |
> | **Owns** | program OKRs, domain map, feature inventory, requirements index, design principles, architecture decisions, design patterns, reading paths, top-level taxonomy |
> | **Depends on** | — |
> | **Extends** | — |
> | **Supersedes** | legacy specs absorbed during consolidation (see 21-deferred-features.md) |
> | **Read after** | — |
> | **Read before** | 01-package-structure.md |
> | **Not owned here** | implementation contracts of each subsystem — see §5 (feature inventory) for the canonical owner of every concept |
> | **Last reviewed** | 2026-04-29 |

## 1. What problem does it solve?

`pyarnes_swarm` is the successor to the 5-package pyarnes monorepo. It collapses pyarnes-core, pyarnes-harness, pyarnes-guardrails, pyarnes-bench, and pyarnes-tasks into one installable package with a flat, auditable structure.

AI coding agents (Claude Code, Cursor, Codex) generate tool calls but have no built-in system for retrying flaky operations, feeding errors back so the model self-corrects, enforcing safety limits, tracking session state, logging events as structured JSONL, routing trivial work to cheap models, or coordinating multiple agents across OS processes. `pyarnes_swarm` provides all of these behind a single `Swarm` entry point.

The legacy monorepo had three compounding problems that drive this consolidation:

1. **Cross-package import friction.** `pyarnes_harness` re-exported `GuardrailChain` from `pyarnes_guardrails` because users thought in one package, not five. Every cross-package boundary was a place for import aliasing to drift.
2. **Duplicated observability.** `core/observe/` (transport) and `core/observability/` (domain events) existed as two separate directories with a one-way dependency between them. Six files served one layered concern.
3. **Scattered public API.** Adopters needed to import from five namespaces to wire up a basic loop. The 80%-case "Hello World" required knowing which symbols lived in which package.

```python
# Before: 5 packages, 5 imports
from pyarnes_core.types import ToolHandler, ModelClient
from pyarnes_harness.loop import AgentLoop, LoopConfig
from pyarnes_guardrails import GuardrailChain, PathGuardrail
from pyarnes_bench import EvalSuite

# After: 1 package, 8 top-level symbols
from pyarnes_swarm import (
    Swarm, AgentSpec, LoopConfig, GuardrailChain,
    ToolRegistry, ModelClient, InMemoryBus, configure_logging,
)
```

## 2. How to read this spec

This overview is structured top-down so the program can be understood at four progressively concrete levels, followed by reference and operational material.

| Section | Reader question it answers |
|---|---|
| 3. Objectives & Key Results | _Why_ are we building this, and how will we know it worked? |
| 4. Domains | _What bounded contexts_ does the program decompose into? |
| 5. Features by domain × OKR | _Which capabilities_ live in each domain, and which OKR does each capability serve? |
| 6. Requirements by domain / feature / OKR | _What testable contracts_ must each feature deliver? |
| 7. Tool-dispatch diagram | _How_ does a single iteration flow at runtime? |
| 8–10. Design principles, ADRs, patterns | _Which conventions_ are non-negotiable, and why? |
| 11. When to use `pyarnes_swarm` | Should I pick this over LangGraph / AutoGen / smolagents / a raw loop? |
| 12. Migration from monorepo | What changes when I move my code from the legacy 5-package layout? |
| 13. Spec inventory & reading paths | Where do I read next, and in which order? |
| 14. Consolidation phase sequence | Which phase are we in, and what gates the next phase? |

If you read only one spec after this one, read [07-swarm-api.md](07-swarm-api.md) — it is the canonical runtime story.

---

## 3. Objectives & Key Results

The OKRs below define what _success_ for the consolidation looks like. Every spec in `specs/consolidation/` exists to deliver at least one Key Result. **SMART** here means: **S**imple (one sentence), **M**easurable (one number / boolean / artifact), **A**chievable (within the named phase), **R**easonable (proportionate to engineering cost), **T**ransactional (asserted at a specific commit / phase boundary).

Anchored measurement vocabulary: `capacity_threshold = 0.75`, `Budget.max_tokens`, `max_retries ≤ 2`, `pass_rate ≥ 0.80`, `cost_efficiency = average_score / total_cost * 100`, Tier 1/2/3 use-case taxonomy, 2³ ablation matrix, Phase 0/1/2/3 gates.

### O1 — Be the runtime that pragmatic teams reach for when they need cost-aware safety guarantees

_Win the segment exhausted by "5 packages, 5 imports" frameworks but who need more than a raw tool-calling loop. The 80%-case Hello World should fit on one screen and run in under 15 minutes._

| KR | Target | Measured by | Time-bound to |
|---|---|---|---|
| **KR1.1** | Adopter time-to-first-working-CLI ≤ 15 minutes from `uvx copier copy ...` | 5 fresh-installer dry-runs documented in `docs/getting-started/distribution.md` walkthrough timings | End of Phase 3 |
| **KR1.2** | Public API enumerated in `__all__` is **exactly 8 named symbols**: `{Swarm, AgentSpec, LoopConfig, GuardrailChain, ToolRegistry, ModelClient, InMemoryBus, configure_logging}` — every other public symbol reachable only via sub-module path (`pyarnes_swarm.ports`, `.errors`, `.agent`, `.guardrails`, `.bench`, `.routing`) | `tests/swarm/test_public_api_size.py` asserts both `len(pyarnes_swarm.__all__) == 8` and the set equality | Phase 2 close |
| **KR1.3** | 0 cross-package re-exports remain post-cutover | `grep -r "from pyarnes_(core\|harness\|guardrails\|bench\|tasks)" packages/ tests/swarm/ tests/features/` returns empty | Phase 3 close |
| **KR1.4** | The five legacy packages are deleted in the cutover commit | `git diff Phase2-tag..Phase3-tag --stat` shows all five `packages/{core,harness,guardrails,bench,tasks}/` removed; CI green | Phase 3 close |

### O2 — Cut median agent-task cost by a third without sacrificing output quality

_Cost-aware routing is not just an architectural feature — it is the competitive wedge. If we don't beat single-model baselines on cost-efficiency, we have failed regardless of how clean the API is._

| KR | Target | Measured by | Time-bound to |
|---|---|---|---|
| **KR2.1** | `cost_efficiency = average_score / total_cost * 100` improves ≥ 30% vs single-model baseline (e.g. GPT-4) on the full bench corpus across Tier 1, 2, 3 | `tests/bench/test_cost_efficiency_uplift.py` snapshot vs baseline run | End of Phase 2 |
| **KR2.2** | 100% of `ModelClient` dispatches measure context with `litellm.token_counter()` _before_ the call | `tests/swarm/test_token_counter_called_before_every_model_call.py` | Phase 2 close |
| **KR2.3** | `MessageCompactor` triggers within ≤ 1 iteration of `tokens / context_window >= 0.75` | `tests/swarm/test_message_compactor_threshold.py` | Phase 2 close |
| **KR2.4** | `Budget.max_tokens` overrun terminates the loop within ≤ 1 iteration of breach (no silent overshoot) | `tests/swarm/test_budget_termination.py` | Phase 2 close |

### O3 — Eliminate the failure modes that make agentic systems unsafe to ship

_Take production-blocking failures off the table by construction, not by vigilance. Secret leaks, runaway loops, and unhandled exception categories should be impossible — not "carefully avoided"._

| KR | Target | Measured by | Time-bound to |
|---|---|---|---|
| **KR3.1** | 0 secrets present in the cutover SHA | `gitleaks` clean run in CI on the merge SHA | Phase 3 close |
| **KR3.2** | 100% of caught exceptions in `packages/swarm/` map to one of the four taxonomy types | `ruff` rule banning bare `except:` outside the loop's top-level boundary; AST audit script in CI | Phase 2 close |
| **KR3.3** | No `os.getenv` reads for secret names in `packages/swarm/` | `grep -rn "os.getenv" packages/swarm/ \| grep -v test/` returns empty | Phase 2 close |
| KR3.4 | `MessageBus` sustains ≥ 100 concurrent multi-process writers with 0 contention errors | Load test `tests/swarm/test_message_bus_concurrent.py` over a 60-second window | Phase 2 close |
| KR3.5 | Every `Swarm.run()` invocation passes through `SanitizePipeline` before tool dispatch | Integration test asserting pipeline ordering | Phase 2 close |

### O4 — Make every benchmark run improve the next one

_Turn the eval suite into a learning system. Routing weights are not fixed — they are the delta of cost-efficiency observed in the previous run. If the loop is not closed, all of O2 is sand-castle._

| KR | Target | Measured by | Time-bound to |
|---|---|---|---|
| KR4.1 | `LLMCostRouter.observe()` accepts every `ScoreResult` from `EvalSuite.run()` and produces a non-zero weight delta when input scores differ | Snapshot test on weight-delta after one bench run | Phase 2 close |
| KR4.2 | `RunReport` is persisted for 100% of `Swarm.run()` invocations to `.pyarnes/runs/<run_id>/` (incl. `ToolCallEntry` per dispatch) | `tests/swarm/test_run_report_persisted.py` over a 10-run window | Phase 2 close |
| KR4.3 | `pass_rate ≥ 0.80` on the bench corpus across all three Tiers | `assert eval_result.pass_rate >= 0.80` in `tests/bench/test_agent_quality.py` | End of Phase 2 |
| KR4.4 | The 2³ ablation matrix (model swap × compaction on/off × guardrails on/off) reports a non-null `cost_efficiency` delta for each of the 8 cells | `tests/bench/test_ablation_matrix.py` | End of Phase 2 |

### O5 — Ship every line through TDD with no silent regressions

_Discipline is architecture, not policy. Two test suites for the same module are conflicting specs, not extra safety._

| KR | Target | Measured by | Time-bound to |
|---|---|---|---|
| KR5.1 | Phase 1 close commit has 100% RED tests | `uv run tasks test` exit code ≠ 0 on the Phase 1 close SHA | Phase 1 close |
| KR5.2 | Phase 2 close commit has 100% GREEN | `uv run tasks check` (lint + typecheck + test) exits 0 on the Phase 2 close SHA | Phase 2 close |
| KR5.3 | 100% of legacy `tests/unit/` files mapped MIGRATE-or-DELETE in `03-test-map.md` are removed at cutover | `git rm` count in the cutover commit matches the map's MIGRATE+DELETE row count | Phase 3 close |
| KR5.4 | 0 BDD scenarios in `tests/features/` duplicate scenarios in `tests/swarm/` | Unique-name lint rule asserted in CI | Phase 2 close |

---

## 4. Domains

The OKRs decompose into 12 bounded contexts plus an appendix. Each domain is a stable home for a related cluster of features and tests; cross-domain interaction happens only through the Ports defined in `ports.py`.

| # | Domain | Primary OKR | Supporting OKRs | One-line role | Specs |
|---|---|---|---|---|---|
| **D1** | Public Surface & Lifecycle | O1 | O5 | Package layout, public API, `Swarm` / `AgentSpec` / `AgentRuntime`, lifecycle FSM | 01, 07 |
| **D2** | Cost Engine | O2 | O4 | Token counting, compaction, budget caps, model routing, provider catalog | 06, 08, 13 |
| **D2b** | Transport | O2 | O1 | Wire-protocol adapter (`ProviderTransport`, `LiteLLMTransport`) — _not_ cost reasoning | 12 |
| **D3** | Coordination Backbone | O3 | O2 | `MessageBus` Protocol + Turso / InMemory / NATS implementations | 05 |
| **D4** | Safety & Trust | O3 / O4 | O1 | Secrets, sanitization, injection guardrails | 11, 14 |
| **D4b** | Extensibility & Hooks | O4 | O5 | Internal Python hooks + external Claude Code lifecycle hooks | 09, 10 |
| **D5** | Evaluation Loop | O4 | O2 | Bench scoring, run logger; 22 + 23 are reference appendices | 15, 16 (refs: 22, 23) |
| **D6** | Quality Discipline | O5 | O1 | Test strategy, test map, dead-code audit, tooling artifacts | 02, 03, 04, 17 |
| **D7a** | API Governance | O1 | O5 | Semver, breaking-change rules, `__all__` enforcement of the 8-symbol surface | 18 |
| **D7b** | Template Governance | O1 | — | Copier template evolution, adopter migration, `pyarnes_ref` pinning | 19 |
| **D7c** | Documentation Governance | O1 | — | Docs-site audience split, onboarding entry pages, semver discoverability | 24 |
| **D8** | Optional Subsystems | (off-path) | O4 | Code-review graph package | 20 |
| **Appendix** | Absorbed-spec index | — | — | Redirect-only index of legacy specs to canonical homes | 21 |

**Why the splits (D2 / D2b, D4 / D4b, D7a / D7b / D7c):**
- **D2b (Transport) split from D2 (Cost Engine)** because transport is a wire-layer adapter, not cost reasoning. It serves the router but is also the layer adopters customise to add a private model gateway.
- **D4b (Hooks) split from D4 (Safety & Trust)** because hooks are an _extensibility_ surface (telemetry, tracing, project-specific gates). Treating them only as safety understates their role.
- **D7a / D7b** because library-API semver and Copier-template versioning ship to different consumers on different release cadences.
- **D7c (Documentation Governance)** because docs-site audience split and semver discoverability are editorial/distribution policy, not library-API or template-versioning mechanics.

---

## 5. Features by Domain × OKR

Each feature is owned by exactly one spec and serves one primary OKR (with possible supporting OKRs). When you need to know _where_ a capability lives, this table is the index.

### D1 — Public Surface & Lifecycle

| Feature | Spec | Primary KR | Supporting KRs |
|---|---|---|---|
| Public API surface (8-symbol top-level) | [07-swarm-api.md](07-swarm-api.md) | KR1.2 | KR1.3, KR2.2 |
| Package structure & flat layout | [01-package-structure.md](01-package-structure.md) | KR1.1, KR1.3 | KR5.4 |
| Lifecycle FSM | [07-swarm-api.md](07-swarm-api.md) | KR1.4 | — |

### D2 — Cost Engine

| Feature | Spec | Primary KR | Supporting KRs |
|---|---|---|---|
| `ModelRouter` (RuleBased + LLMCost) | [06-model-router.md](06-model-router.md) | KR2.1 | KR4.1 |
| Token counting, compaction, budget caps | [08-token-budget.md](08-token-budget.md) | KR2.2, KR2.3, KR2.4 | — |
| Provider catalog (OpenRouter, HF, NIM, Anthropic) | [13-provider-config.md](13-provider-config.md) | KR2.1 | KR3.3 |

### D2b — Transport

| Feature | Spec | Primary KR | Supporting KRs |
|---|---|---|---|
| `ProviderTransport` Protocol + `LiteLLMTransport` | [12-transport.md](12-transport.md) | KR2.2 | KR3.2 |

### D3 — Coordination Backbone

| Feature | Spec | Primary KR | Supporting KRs |
|---|---|---|---|
| `MessageBus` (Turso MVCC default; InMemory + NATS optional) | [05-message-bus.md](05-message-bus.md) | KR3.4 | KR4.2 |

### D4 — Safety & Trust

| Feature | Spec | Primary KR | Supporting KRs |
|---|---|---|---|
| `SanitizePipeline` + `InjectionGuardrail` | [11-message-safety.md](11-message-safety.md) | KR3.5 | KR3.2 |
| Secrets via OS keychain (`SecretStore`, `KeyringSecretStore`, redaction) | [14-secrets.md](14-secrets.md) | KR3.1, KR3.3 | — |

### D4b — Extensibility & Hooks

| Feature | Spec | Primary KR | Supporting KRs |
|---|---|---|---|
| Internal Python hooks (`PreToolHook`, `PostToolHook`, steering queue) | [09-loop-hooks.md](09-loop-hooks.md) | KR1.4 | KR4.2 |
| External Claude Code lifecycle hooks (`PreToolUse`, `PostToolUse`, `Stop`, …) | [10-hook-integration.md](10-hook-integration.md) | KR4.2 | KR1.4 |

### D5 — Evaluation Loop

| Feature | Spec | Primary KR | Supporting KRs |
|---|---|---|---|
| Bench-integrated scoring axes (`Scorer`, `EvalSuite.run()`, `cost_efficiency`) | [15-bench-integrated-axes.md](15-bench-integrated-axes.md) | KR4.1, KR4.3, KR4.4 | KR2.1 |
| Run logger (`RunReport`, `EvalRunLogger`, `.pyarnes/runs/<run_id>/`) | [16-run-logger.md](16-run-logger.md) | KR4.2 | — |
| Reference: Tier 1/2/3 + 2³ ablation matrix | [22-evaluation-taxonomy.md](22-evaluation-taxonomy.md) | (reference) | KR4.4 |
| Reference: Claude Code judge plugin (deferred) | [23-claude-judge-plugin.md](23-claude-judge-plugin.md) | (deferred) | — |

### D6 — Quality Discipline

| Feature | Spec | Primary KR | Supporting KRs |
|---|---|---|---|
| TDD cycle (RED → GREEN → REFACTOR per module) | [02-test-strategy.md](02-test-strategy.md) | KR5.1, KR5.2 | — |
| Legacy test migration map (MIGRATE / DELETE / KEEP) | [03-test-map.md](03-test-map.md) | KR5.3 | — |
| Dead-code audit (three-pass method) | [04-dead-code-audit.md](04-dead-code-audit.md) | KR1.4 | KR5.3 |
| Managed-artifacts policy & repo hygiene | [17-tooling-artifacts.md](17-tooling-artifacts.md) | KR5.4 | — |

### D7a — API Governance

| Feature | Spec | Primary KR | Supporting KRs |
|---|---|---|---|
| Semver, breaking-change rules, `__all__` enforcement | [18-api-surface-governance.md](18-api-surface-governance.md) | KR1.2 | KR5.4 |

### D7b — Template Governance

| Feature | Spec | Primary KR | Supporting KRs |
|---|---|---|---|
| Copier template evolution & `pyarnes_ref` pinning | [19-template-version-control.md](19-template-version-control.md) | KR1.1 | — |

### D7c — Documentation Governance

| Feature | Spec | Primary KR | Supporting KRs |
|---|---|---|---|
| Docs audience split, onboarding entry pages, semver discoverability | [24-documentation-governance.md](24-documentation-governance.md) | KR1.1 | KR1.2 |

### D8 — Optional Subsystems

| Feature | Spec | Primary KR | Supporting KRs |
|---|---|---|---|
| `pyarnes_bench.audit` subpackage (tree-sitter parser, dead-code/cycle/complexity audits) | [20-graph-package.md](20-graph-package.md) | (off-path) | KR4.4 |

### Appendix

| Feature | Spec | Primary KR | Supporting KRs |
|---|---|---|---|
| Absorbed-legacy-specs index | [21-deferred-features.md](21-deferred-features.md) | — | — |

---

## 6. Requirements by Domain / Feature / OKR

Each requirement below is a testable contract pulled from the feature's owning spec. This section is the _index_, not the source of truth — full acceptance criteria live in each linked spec.

### D1 — Public Surface & Lifecycle

**Public API surface — [07-swarm-api.md](07-swarm-api.md) → KR1.2, KR1.3**
- Top-level `pyarnes_swarm.__all__` is exactly the 8-symbol set: `{Swarm, AgentSpec, LoopConfig, GuardrailChain, ToolRegistry, ModelClient, InMemoryBus, configure_logging}`.
- All other public symbols reachable only via sub-module path: `pyarnes_swarm.ports`, `.errors`, `.agent`, `.guardrails`, `.bench`, `.routing`.
- Hello World runs in a single import block; no sub-module imports required for the 80% case.

**Package structure — [01-package-structure.md](01-package-structure.md) → KR1.1, KR1.3**
- Single installable package; one `pyarnes_swarm/ports.py` post-consolidation (current monorepo: 4 subsystem ports.py files — see ADR §9).
- `core/observe/` and `core/observability/` collapsed into one observability subsystem.
- All cross-package re-exports removed.

**Lifecycle FSM — [07-swarm-api.md](07-swarm-api.md) → KR1.4**
- Every session has a tracked state machine (running / paused / done).
- Invalid transitions raise; valid transitions are enumerated in `_VALID_TRANSITIONS`.

### D2 — Cost Engine

**`ModelRouter` — [06-model-router.md](06-model-router.md) → KR2.1, KR4.1**
- Routes by complexity signals through a three-filter pipeline (context window → complexity → cost).
- `LLMCostRouter.observe()` accepts `ScoreResult` and updates routing weights (Observer pattern; planned, not yet in code).
- Strategy implementations are swappable without changing the loop.

**Token budget — [08-token-budget.md](08-token-budget.md) → KR2.2, KR2.3, KR2.4**
- `litellm.token_counter()` measures context before every model call (microsecond hot loop).
- `MessageCompactor.compact()` triggers when `tokens / context_window >= 0.75`.
- `Budget.max_tokens` enforces a hard cumulative cap; loop terminates within ≤ 1 iteration of breach.
- Output-token estimation uses heuristics calibrated at startup with `acount_tokens()`; P95 of observed outputs replaces heuristics post-warm-up.

**Provider catalog — [13-provider-config.md](13-provider-config.md) → KR2.1, KR3.3**
- Supports OpenRouter, HuggingFace Inference, NVIDIA NIM, Anthropic Direct.
- Provider prefix resolution; switching providers is a configuration change.

### D2b — Transport

**`ProviderTransport` — [12-transport.md](12-transport.md) → KR2.2, KR3.2**
- A single transport boundary owns provider error mapping into the four-type error taxonomy.
- LiteLLM-backed by default; raw transport is a configuration choice.

### D3 — Coordination Backbone

**`MessageBus` — [05-message-bus.md](05-message-bus.md) → KR3.4, KR4.2**
- Turso/Limbo (MVCC) is the default backend; sustains ≥ 100 concurrent writers without WAL contention.
- NATS JetStream available as an optional extra.
- Messaging is durable across process restarts; resume-from-offset semantics specified.

### D4 — Safety & Trust

**`SanitizePipeline` & `InjectionGuardrail` — [11-message-safety.md](11-message-safety.md) → KR3.5, KR3.2**
- Sanitization (input H6) precedes guardrails (output H8); ordering is enforced by integration test.
- Bus messages cannot escalate via downstream consumers.

**Secrets — [14-secrets.md](14-secrets.md) → KR3.1, KR3.3**
- Backed by OS keychain through `KeyringSecretStore`; `EnvSecretStore` and `ChainedSecretStore` available as fallbacks.
- No `.env` reads in runtime path.
- `get()` raises `KeyError` on missing key — fail at lookup, not at the API call 1000 tokens later.
- Credential redaction policy (H9) applied to all log output.

### D4b — Extensibility & Hooks

**Internal Python hooks — [09-loop-hooks.md](09-loop-hooks.md) → KR1.4, KR4.2**
- `PreToolHook` and `PostToolHook` Protocols expose pre/post-iteration extension points.
- Steering queue allows in-process injection without forking the runtime.

**External Claude Code lifecycle hooks — [10-hook-integration.md](10-hook-integration.md) → KR4.2, KR1.4**
- Stdin JSON contract compatible with Claude Code, Cursor, and Codex.
- Exit-code semantics specified for `PreToolUse` / `PostToolUse` / `Stop` (and any additional template-only hooks).
- `.pyarnes/` directory layout supports per-branch lifecycle isolation.

### D5 — Evaluation Loop

**Bench-integrated axes — [15-bench-integrated-axes.md](15-bench-integrated-axes.md) → KR4.1, KR4.3, KR4.4**
- `ScoreResult` flows Scorer → `EvalSuite.run()` → `cost_efficiency` → `LLMCostRouter.observe()` without bespoke glue.
- `pass_rate >= 0.80` enforced in `tests/bench/test_agent_quality.py`.
- 2³ ablation matrix produces 8 non-null `cost_efficiency` deltas.

**Run logger — [16-run-logger.md](16-run-logger.md) → KR4.2**
- Every `Swarm.run()` produces a `RunReport` persisted to `.pyarnes/runs/<run_id>/` as JSONL.
- `ToolCallEntry` is appended per tool dispatch; dual-source normalization specified.

### D6 — Quality Discipline

**TDD cycle — [02-test-strategy.md](02-test-strategy.md) → KR5.1, KR5.2**
- Each module has a failing test before any implementation lands.
- `tests/swarm/` owns unit-level contracts; `tests/features/` owns user-visible BDD scenarios.

**Test migration map — [03-test-map.md](03-test-map.md) → KR5.3**
- Every legacy `tests/unit/` file is mapped MIGRATE / DELETE / KEEP.
- No legacy test survives Phase 3 without an explicit decision.

**Dead-code audit — [04-dead-code-audit.md](04-dead-code-audit.md) → KR1.4, KR5.3**
- Three-pass method: `vulture` → callee trace → cognitive complexity.
- Old tests deleted after Refactor; overlapping suites are conflicting specs, not extra safety.

**Managed artifacts — [17-tooling-artifacts.md](17-tooling-artifacts.md) → KR5.4**
- Lint, typecheck, and coverage outputs have a stable shape consumable by hooks.
- `.gitignore` rules and template scaffolding exclusions documented.

### D7a — API Governance

**Semver & `__all__` enforcement — [18-api-surface-governance.md](18-api-surface-governance.md) → KR1.2, KR5.4**
- `__all__` is the contract; reordering or adding without bumping a version number is a breaking change.
- Deprecation policy stub specified for symbols leaving the 8-symbol surface.

### D7b — Template Governance

**Copier template evolution — [19-template-version-control.md](19-template-version-control.md) → KR1.1**
- `pyarnes_ref` pins template clients to a known runtime version (default `main` until first stable release; pin to a tag thereafter).
- Template-level breaking changes are a separate SemVer track from the library.

### D7c — Documentation Governance

**Documentation governance — [24-documentation-governance.md](24-documentation-governance.md) → KR1.1, KR1.2**
- `docs/getting-started/distribution.md` is the canonical adopter onboarding page.
- `docs/architecture/meta-use.md` owns the dual-use runtime + dev-time harness story.
- Semver policy discoverability is surfaced through documentation entry points while the underlying policy remains owned by `18-api-surface-governance.md`.

### D8 — Optional Subsystems

**`pyarnes_bench.audit` subpackage — [20-graph-package.md](20-graph-package.md) → off-path**
- In-tree, LLM-free, Python-only code-graph + audit tool inside `pyarnes_bench`.
- Phase 1: tree-sitter-python → networkx → JSON; eight detectors (unused files / exports / deps, circular imports, duplicate blocks, complexity, boundaries, feature flags); four `tasks audit:*` entries.
- Phase 2 (deferred, opt-in extras): libsql persistence, Leiden communities, Jinja2 report, stdio MCP server.

### Appendix

**Absorbed-legacy-specs index — [21-deferred-features.md](21-deferred-features.md) → —**
- Maps every legacy spec (PR-01..PR-06, harness-feature-expansion, etc.) to its canonical consolidation home.

---

## 7. Tool-dispatch and error-routing (canonical diagram)

Each iteration begins with a token count check. Context grows with every tool result appended to history; without compaction, cost is O(n²) in iterations. `litellm.token_counter()` measures the current context before every model call and triggers `MessageCompactor` when the threshold is reached.

> **Diagram:** [Tool dispatch sequence](diagrams/00-tool-dispatch.html). The ASCII version below is preserved for terminal/grep use; the linked HTML diagram is the canonical version and supersedes the ASCII when the two disagree.

```
User message
    │
    ▼
AgentLoop.run()
    │
    ├─► litellm.token_counter(messages)          ← measure BEFORE every model call
    │        │ tokens / context_window >= 0.75 → MessageCompactor.compact()
    │        │   (summarise old messages → keep context cost bounded)
    │        │ cumulative_tokens >= Budget.max_tokens → stop (hard token cap)
    │        │
    │        ▼
    ├─► ModelClient.next_action() ──► tool_call or final_answer
    │        │
    │        ▼
    │   GuardrailChain.check()
    │        │ violation → UserFixableError (bubble up to human)
    │        │
    │        ▼
    │   ToolHandler.execute()
    │        │ TransientError → retry (max_retries ≤ 2)
    │        │ LLMRecoverableError → ToolMessage (model self-corrects)
    │        │ UserFixableError → interrupt (loop stops)
    │        │ UnexpectedError → bubble up (page on-call)
    │        │
    │        ▼
    │   ToolMessage appended to history; iteration counter++
    │
    ▼
final_answer → return messages
```

Two complementary controls:
- `MessageCompactorConfig.capacity_threshold = 0.75` — keeps any single request's context small (per-request cost)
- `Budget.max_tokens` — caps total token spend across the whole session (cumulative cost)

Both use `litellm.token_counter()` as the measurement primitive.

---

## 8. Cross-cutting design principles (the Six)

Each principle is enforced in current monorepo code; the cited file:line is the canonical witness.

1. **Async-first** — all tool execution uses `asyncio` to avoid GIL contention.
   - Evidence: `packages/harness/src/pyarnes_harness/loop.py:1-22`; `packages/harness/src/pyarnes_harness/budget.py:32` (`_lock: asyncio.Lock`).
2. **Structured logging** — every event emitted as JSONL on stderr via `loguru`.
   - Evidence: `packages/core/src/pyarnes_core/observe/logger.py:67-76` (`_json_sink` writes one JSON line per event; default stream is `sys.stderr`).
3. **Error taxonomy** — four error types: retry (`TransientError`), feed back (`LLMRecoverableError`), interrupt (`UserFixableError`), bubble up (`UnexpectedError`).
   - Evidence: `packages/core/src/pyarnes_core/errors.py:21-28` (`__all__` enumerates exactly these four plus `HarnessError` base + `Severity`).
4. **Composable guardrails** — safety checks stack via `GuardrailChain`; first violation wins.
   - Evidence: `packages/guardrails/src/pyarnes_guardrails/guardrails.py:268-293`.
5. **Lifecycle FSM** — every session has a trackable state machine with guarded transitions.
   - Evidence: `packages/core/src/pyarnes_core/lifecycle.py:58-64` (`_VALID_TRANSITIONS`); `lifecycle.py:96-98` (raises on invalid transition).
6. **No magic** — no decorators, metaclasses, or auto-discovery; explicit wiring only.
   - Evidence: `grep` of `packages/*.py` finds zero metaclass definitions; reinforced by `CLAUDE.md:110-116` and `01-package-structure.md:22`.

---

## 9. Architecture decisions (ADRs)

Each decision below has a rationale — read these before implementing to avoid re-discovering the constraints that produced them.

| Decision | Why |
|---|---|
| **Target**: single `pyarnes_swarm/ports.py` post-consolidation. **Current** (monorepo): 4 subsystem `ports.py` files (dispatch, observability, safety, transport) | One file to read when implementing a custom backend; the current 4-file split is what the consolidation is collapsing |
| `ModelClientPort` (Protocol) not `ModelClient` (ABC) | Model implementations live in different codebases; inheritance would create a cross-package dep |
| Separate OS processes for agents | GIL prevents true parallelism; process isolation prevents cross-agent memory corruption |
| TursoMessageBus with MVCC | Standard SQLite WAL serialises writers; MVCC allows concurrent multi-process writes |
| `Budget` (immutable) ≠ `IterationBudget` (mutable) | One is a value snapshot; the other is a live shared counter — merging them is a type contradiction |
| `get()` raises `KeyError`, not returns `None` | Missing secrets should fail at `store.get()`, not at the API call 1000 tokens later |
| `token_counter()` in the loop, `acount_tokens()` at startup | Hot-loop counting must be microseconds; startup baseline can afford a network call (~100ms) |
| Heuristics for output-token estimation | No library can predict output tokens; heuristics are calibrated estimates, P95 replaces them after warm-up |
| Delete old tests after Refactor | Two test suites for the same module are conflicting specs, not extra safety |
| **Async-safe shared state via `asyncio.Lock`** | Concurrent `consume`/`refund` requires explicit lock — `frozen=True` does not provide it (`packages/harness/src/pyarnes_harness/budget.py:32-61`) |
| **Atomic, mode-`0o600` persistence for hooks/checkpoints** | Crash mid-write must leave the prior file intact; checkpoints contain credentials and state (`packages/core/src/pyarnes_core/lifecycle.py:149-166` via `write_private`; `packages/core/src/pyarnes_core/atomic_write.py`) |
| **`ContextVar`-isolated logging stream** | Async-safe per-task isolation without thread-locals (`packages/core/src/pyarnes_core/observe/logger.py:76-79`) |
| **Stderr-only logging; stdout reserved for tool output** | Mixing stdout/stderr breaks JSONL parseability for downstream agents (`CLAUDE.md:113`; `observe/logger.py:104-106`) |

---

## 10. Design patterns used

| Pattern | Where | Why |
|---|---|---|
| Ports & Adapters (Hexagonal) | `ports.py` + all adapters (current: 4 subsystem ports.py; target: 1 file) | Contracts stay stable when infra changes |
| Protocol (structural typing) | All Ports — e.g. `packages/core/src/pyarnes_core/dispatch/ports.py:23,54,76` (`@runtime_checkable Protocol`) | No inheritance required; structural check at type-check time |
| ABC (abstract base class) | `Guardrail` (`packages/guardrails/src/pyarnes_guardrails/guardrails.py:44`); `Scorer`/`AsyncScorer` (`packages/bench/src/pyarnes_bench/scorer.py:23,84`) | Provides default behaviour + enforces `@abstractmethod` |
| Strategy | `ModelRouter` implementations — _**planned**_ ([06-model-router.md](06-model-router.md)) — not yet in code | Swap routing logic without changing the loop |
| Chain of Responsibility | `GuardrailChain` (`packages/guardrails/src/pyarnes_guardrails/guardrails.py:268-293`) | Each guardrail checks independently; first violation wins |
| Observer | `LLMCostRouter.observe()` — _**planned**_ ([15-bench-integrated-axes.md](15-bench-integrated-axes.md)) — not yet in code | Routing learns from evaluation results |
| Immutable value object | `Budget`, `TaskMeta`, `ScoreResult`, all error types (`packages/core/src/pyarnes_core/errors.py:63,90,106,123,137`; `budget.py:27`) | `frozen=True` prevents accidental mutation across coroutines |
| Mutable shared resource | `IterationBudget` (`packages/harness/src/pyarnes_harness/budget.py:22-61`) | `asyncio.Lock` makes concurrent consume/refund safe |

---

## 11. When to use pyarnes_swarm

| Option | Best fit |
|---|---|
| **pyarnes_swarm** | Teams that want explicit contracts (`ModelClient`, `ToolHandler`) and composable guardrails, with cost-aware routing across providers |
| LangGraph | Complex graph/state orchestration with rich ecosystem integrations |
| AutoGen | Multi-agent conversations and role-based collaboration patterns |
| smolagents | Very fast prototyping with lightweight agent APIs |
| Raw tool-calling loop | Maximum custom behavior and zero framework coupling |

`pyarnes_swarm` sits between "raw loop" and "full framework." It provides a tested execution loop, explicit error taxonomy, structured JSONL logging, opt-in guardrail composition, and cost-aware routing without hiding core control flow.

---

## 12. Migration from monorepo

Old import → new import:

| Old | New |
|---|---|
| `from pyarnes_core.types import ToolHandler` | `from pyarnes_swarm.ports import ToolHandler` |
| `from pyarnes_core.types import ModelClient` | `from pyarnes_swarm.ports import ModelClientPort` (Protocol) or `from pyarnes_swarm import ModelClient` (concrete) |
| `from pyarnes_core.errors import TransientError` | `from pyarnes_swarm.errors import TransientError` |
| `from pyarnes_harness.loop import AgentLoop, LoopConfig` | `from pyarnes_swarm import LoopConfig`. **`AgentLoop` is internal post-consolidation** — adopters use `Swarm` instead. |
| `from pyarnes_guardrails import GuardrailChain` | `from pyarnes_swarm import GuardrailChain` |
| `from pyarnes_bench import EvalSuite` | `from pyarnes_swarm.bench import EvalSuite` |

---

## 13. Spec inventory and reading paths

> If you read only one spec, read [07-swarm-api.md](07-swarm-api.md). It is the canonical runtime story; 05-message-bus and 06-model-router are supporting internals, not peers.

### Inventory by group (specs 00–24)

| Group | Specs | Role |
|---|---|---|
| **core-runtime** | 00, 01, 05, 06, 07, 08, 12 | The minimum reading set to understand how the system runs. |
| **safety-extensibility** | 09, 10, 11, 14 | Internal hooks, external hooks, sanitization, secrets. |
| **evaluation-capture** | 15, 16 | Bench scoring and run persistence. |
| **governance** | 18, 19, 24 | API surface, template-evolution, and documentation/discoverability policy. |
| **testing-quality** | 02, 03, 04, 17 | TDD strategy, test-migration map, dead-code audit, tooling artifacts. |
| **optional-subsystem** | 20 | Code-review graph package — opt-in, not part of the minimum runtime. |
| **historical-appendix** | 21 | Absorbed / deferred specs kept for traceability. |
| **reference** | 22, 23 | Tier taxonomy + judge plugin (deferred). |

### Reading paths

File ids stay numeric for stable links, but the recommended reading order is not purely numeric. The testing stack is intentionally pulled forward so the rest of the consolidation is read through migration discipline rather than as an isolated runtime redesign.

- **Architecture path** (top-down system understanding):
  `00 → 01 → 02 → 03 → 04 → 05 → 06 → 07 → 08 → 09 → 10 → 11 → 12 → 13 → 14 → 15 → 16 → 17 → 18 → 19 → 20`
- **Adopter onboarding path** (ship a working CLI fast):
  `00 → 01 → 07 → 14 → 13 → 10`
- **Documentation / distribution path** (docs-site audience split and semver discoverability):
   `00 → 18 → 19 → 24`

### Dependency map

The table below is the current machine-readable dependency summary used by the local specs viewer. Per-spec `Depends on:` headers remain the authoritative source of truth for ownership and edge semantics.

| Spec | Read before |
|---|---|
| **01** Package structure | 05, 06, 07, 08, 10, 13, 14, 15, 16, 18 |
| **05** Message bus | 07 |
| **06** Model router | 07, 08, 12, 13 |
| **07** Swarm API | 09, 10, 15, 16, 18 |
| **08** Token budget | 06, 07, 15, 16 |
| **09** Loop hooks | 07, 10 |
| **10** Hook integration | 09, 15, 16 |
| **12** Transport | 06, 13, 14 |
| **13** Provider config | 06, 12, 14 |
| **14** Secrets | 07, 12, 13 |
| **15** Bench integrated axes | 08, 16, 20 |
| **16** Run logger | 10, 15, 20 |
| **18** API surface governance | 01, 07 |
| **20** Graph package | 10, 15, 16 |

---

## 14. Consolidation phase sequence (do in order)

Each phase must complete before the next begins. Do not run phases in parallel.

| Phase | What happens | When done |
|---|---|---|
| **0 — Specs** | Write and maintain the canonical consolidation specs; archive old specs; delete `docs/` | ✅ Complete |
| **1 — RED tests** | Create `packages/swarm/` skeleton; write the new `tests/swarm/` and `tests/features/` coverage; confirm 100% fail | Next step |
| **2 — GREEN + REFACTOR** | Implement each module (Red → Green → Refactor per module); delete old tests after each module's refactor | |
| **3 — Cutover** | Delete dead code; delete old packages; confirm only the new `tests/swarm/` and `tests/features/` suites remain for the consolidated runtime | |

Start a fresh context window for Phase 1 onwards to avoid context exhaustion mid-implementation.

Distribution and documentation strategy (audience split, `docs/getting-started/distribution.md`, `docs/architecture/meta-use.md`, semver discoverability) is owned by [24-documentation-governance.md](24-documentation-governance.md).
