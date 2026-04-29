# pyarnes_swarm — Consolidation Overview

> **Spec header**
>
> | Field | Value |
> |---|---|
> | **Title** | pyarnes_swarm — Consolidation Overview |
> | **Status** | active |
> | **Type** | core-runtime |
> | **Owns** | portfolio map, reading paths, spec inventory, top-level taxonomy, design principles index |
> | **Depends on** | — |
> | **Extends** | — |
> | **Supersedes** | legacy specs absorbed during consolidation (see 14-deferred-features.md for mapping) |
> | **Read after** | — |
> | **Read before** | 01-package-structure.md |
> | **Not owned here** | implementation contracts of each subsystem — see the inventory table above for the canonical owner of every concept |
> | **Extended by** | 01-package-structure.md, 14-deferred-features.md |
> | **Last reviewed** | 2026-04-29 |

## What problem does it solve?

`pyarnes_swarm` is the successor to the 5-package pyarnes monorepo. It collapses pyarnes-core, pyarnes-harness, pyarnes-guardrails, pyarnes-bench, and pyarnes-tasks into one installable package with a flat, auditable structure.

The monorepo had three compounding problems:

1. **Cross-package import friction.** `pyarnes_harness` re-exported `GuardrailChain` from `pyarnes_guardrails` because users thought in one package, not five. Every cross-package boundary was a place for import aliasing to drift.

2. **Duplicated observability.** `core/observe/` (transport) and `core/observability/` (domain events) existed as two separate directories with a one-way dependency between them. Six files served one layered concern.

3. **Scattered public API.** Adopters needed to import from five namespaces to wire up a basic loop. The 80%-case "Hello World" required knowing which symbols lived in which package.

## Intended outcome

```python
# Before: 5 packages, 5 imports
from pyarnes_core.types import ToolHandler, ModelClient
from pyarnes_harness.loop import AgentLoop, LoopConfig
from pyarnes_guardrails import GuardrailChain, PathGuardrail
from pyarnes_bench import EvalSuite

# After: 1 package, 1 import
from pyarnes_swarm import AgentRuntime, LoopConfig, GuardrailChain, Swarm
```

## Goals

1. Single installable package — `pip install pyarnes_swarm`
2. ~10-symbol public API covering the 80% use case
3. `ModelRouter` routes agent tasks to cheap/expensive models based on complexity signals
4. `MessageBus` backed by Turso/Limbo (embedded, MVCC) for durable inter-process messaging; NATS JetStream as optional extra
5. All dead code removed; two overlapping observability subsystems merged into one
6. Existing implemented specs archived; new `specs/consolidation/` specs are canonical
7. Multi-provider routing — OpenRouter, HuggingFace Inference, NVIDIA NIM, Anthropic Direct — through one `ModelClient` interface (LiteLLM-backed; handles text, images, audio, and embeddings)
8. Secrets management via OS keychain (`keyring`) — no `.env` files, no accidental GitHub leaks
9. Evaluation feedback loop: `ScoreResult` flows from `Scorer` → `EvalSuite.run()` → `cost_efficiency` → `LLMCostRouter.observe()`
10. Full TDD discipline — Red → Green → Refactor per module

## What problem does pyarnes_swarm solve?

AI coding agents (Claude Code, Cursor, Codex) generate tool calls but have no built-in system for:

- **Retrying flaky operations** — network timeouts, rate limits
- **Feeding errors back** — so the model can self-correct instead of crashing
- **Enforcing safety limits** — blocking access outside `/workspace`
- **Tracking session state** — knowing if the agent is running, paused, or done
- **Logging everything** — structured JSONL that humans and machines can parse
- **Routing to cheap models** — delegating trivial tasks to small models automatically
- **Durable messaging** — coordinating multiple agents across OS processes

pyarnes_swarm solves all of these with a single `Swarm` entry point.

## When to use pyarnes_swarm

| Option | Best fit |
|---|---|
| **pyarnes_swarm** | Teams that want explicit contracts (`ModelClient`, `ToolHandler`) and composable guardrails, with cost-aware routing across providers |
| LangGraph | Complex graph/state orchestration with rich ecosystem integrations |
| AutoGen | Multi-agent conversations and role-based collaboration patterns |
| smolagents | Very fast prototyping with lightweight agent APIs |
| Raw tool-calling loop | Maximum custom behavior and zero framework coupling |

pyarnes_swarm sits between "raw loop" and "full framework." It gives you a tested execution loop, explicit error taxonomy, structured JSONL logging, opt-in guardrail composition, and cost-aware routing without hiding core control flow.

## Migration from monorepo

Old import → new import:

| Old | New |
|---|---|
| `from pyarnes_core.types import ToolHandler` | `from pyarnes_swarm.ports import ToolHandler` |
| `from pyarnes_core.types import ModelClient` | `from pyarnes_swarm.ports import ModelClientPort` (Protocol) or `from pyarnes_swarm import ModelClient` (concrete) |
| `from pyarnes_core.errors import TransientError` | `from pyarnes_swarm.errors import TransientError` |
| `from pyarnes_harness.loop import AgentLoop, LoopConfig` | `from pyarnes_swarm.agent import AgentLoop, LoopConfig` |
| `from pyarnes_guardrails import GuardrailChain` | `from pyarnes_swarm import GuardrailChain` |
| `from pyarnes_bench import EvalSuite` | `from pyarnes_swarm.bench import EvalSuite` |

## Six design principles (unchanged)

1. **Async-first** — all tool execution uses `asyncio` to avoid GIL contention
2. **Structured logging** — every event is emitted as JSONL on stderr via `loguru`
3. **Error taxonomy** — four error types: retry, feed back, interrupt, bubble up
4. **Composable guardrails** — safety checks stack via `GuardrailChain`
5. **Lifecycle FSM** — every session has a trackable state machine
6. **No magic** — no decorators, metaclasses, or auto-discovery; explicit wiring only

## Tool-dispatch and error-routing (canonical diagram)

Each iteration begins with a token count check. Context grows with every tool result appended to history; without compaction, cost is O(n²) in iterations. `litellm.token_counter()` measures the current context before every model call and triggers `MessageCompactor` when the threshold is reached.

> **Diagram:** [Tool dispatch sequence](diagrams/00-tool-dispatch.html). The ASCII version below is preserved for terminal/grep use; the linked HTML diagram is the canonical version and supersedes the ASCII when the two disagree.

```
User message
    │
    ▼
AgentLoop.run()
    │
    ├─► litellm.token_counter(messages)          ← measure BEFORE every model call
    │        │ tokens / context_window >= threshold → MessageCompactor.compact()
    │        │   (summarise old messages → keep context cost bounded)
    │        │ cumulative_tokens >= Budget.max_tokens → stop (hard token cap)
    │        │
    │        ▼
    ├─► ModelClient.next_action() ──► tool_call or final_answer
    │        │
    │        ▼
    │   GuardrailChain.check()
    │        │ violation → varies per rule (e.g. InjectionGuardrail → LLMRecoverableError → ToolMessage; PathGuardrail → UserFixableError → interrupt)
    │        │
    │        ▼
    │   ToolHandler.execute()
    │        │ TransientError → retry (max_retries)
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
- `MessageCompactorConfig.capacity_threshold` — keeps any single request's context small (per-request cost)
- `Budget.max_tokens` — caps total token spend across the whole session (cumulative cost)

Both use `litellm.token_counter()` as the measurement primitive.

## Key design decisions (why this way)

Each decision below has a rationale — read these before implementing to avoid re-discovering the constraints that produced them.

| Decision | Why |
|---|---|
| Single `ports.py` for all Protocols | One file to read when implementing a custom backend; no scattered interface definitions |
| `ModelClientPort` (Protocol) not `ModelClient` (ABC) | Model implementations live in different codebases; inheritance would create a cross-package dep |
| Separate OS processes for agents | GIL prevents true parallelism; process isolation prevents cross-agent memory corruption |
| TursoMessageBus with MVCC | Standard SQLite WAL serialises writers; MVCC allows concurrent multi-process writes |
| `Budget` (immutable) ≠ `IterationBudget` (mutable) | One is a value snapshot; the other is a live shared counter — merging them is a type contradiction |
| `get()` raises `KeyError`, not returns `None` | Missing secrets should fail at `store.get()` not at the API call 1000 tokens later |
| `token_counter()` in the loop, `acount_tokens()` at startup | Hot-loop counting must be microseconds; startup baseline can afford a network call |
| Heuristics for output token estimation | No library can predict output tokens; heuristics are calibrated estimates, P95 replaces them after warm-up |
| Delete old tests after Refactor | Two test suites for the same module are conflicting specs, not extra safety |

## Design Patterns Used

| Pattern | Where | Why |
|---|---|---|
| Ports & Adapters (Hexagonal) | `ports.py` + all adapters | Contracts stay stable when infra changes |
| Protocol (structural typing) | All Ports | No inheritance required; structural check at type-check time |
| ABC (abstract base class) | `Guardrail`, `Scorer` | Provides default behaviour + enforces `@abstractmethod` |
| Strategy | `ModelRouter` implementations | Swap routing logic without changing the loop |
| Chain of Responsibility | `GuardrailChain` | Each guardrail checks independently; first violation wins |
| Observer | `LLMCostRouter.observe()` | Routing learns from evaluation results |
| Immutable value object | `Budget`, `TaskMeta`, `ScoreResult` | `frozen=True` prevents accidental mutation across coroutines |
| Mutable shared resource | `IterationBudget` | `asyncio.Lock` makes concurrent consume/refund safe |

## Spec inventory and reading paths

> If you read only one spec, read [04-swarm-api.md](04-swarm-api.md). It is the canonical runtime story; 02-message-bus and 03-model-router are supporting internals, not peers.

### Inventory by group (all 24 specs, 00 through 23 inclusive)

| Group | Specs | Role |
|---|---|---|
| **core-runtime** | 00, 01, 02, 03, 04, 12 | The minimum reading set to understand how the system runs. |
| **integrations-safety** | 06, 10, 11, 20, 21, 22 | External hooks, internal hooks, sanitization, transport, providers, secrets. |
| **evaluation-capture** | 07, 13 | Bench scoring and run persistence. |
| **governance** | 16, 17 | Stable API surface and template-evolution policy. |
| **testing** | 05, 08, 09, 15 | Dead-code audit, TDD strategy, test-migration map, tooling artifacts. |
| **optional-subsystem** | 23 | Code-review graph package — opt-in, not part of the minimum runtime. |
| **historical-appendix** | 14, 18, 19 | Absorbed / deferred specs kept for traceability. |

### Reading paths

Two paths cover the two distinct reasons to read these specs.

- **Architecture path** (top-down system understanding):
  `00 → 01 → 02 → 03 → 04 → 12 → 06 → 21 → 20 → 22 → 10 → 11 → 07 → 13 → 23`
- **Adopter onboarding path** (ship a working CLI fast):
  `00 → 04 → 11 → 10 → 06`

### Dependency map

When changing a spec, re-read every spec listed on the right. (Appendix and pure-testing specs are omitted — they have no dependents.)

| Change | Re-read |
|---|---|
| **01** package-structure | 02, 03, 04, 06, 07, 10, 11, 12, 13, 16 |
| **02** message-bus | 04 |
| **03** model-router | 04, 10, 12, 22 |
| **04** swarm-api | 06, 07, 13, 16, 21 |
| **06** hook-integration | 07, 13, 21 |
| **07** bench-integrated-axes | 12, 13, 23 |
| **10** provider-config | 03, 11, 22 |
| **11** secrets | 04, 10, 22 |
| **12** token-budget | 03, 04, 07, 13 |
| **13** run-logger | 06, 07, 23 |
| **16** api-surface-governance | 01, 04 |
| **21** loop-hooks | 04, 06 |
| **22** transport | 03, 10, 11 |
| **23** graph-package | 06, 07, 13 |

## Consolidation sequence (do in order)

Each phase must complete before the next begins. Do not run phases in parallel.

| Phase | What happens | When done |
|---|---|---|
| **0 — Specs** | Write and maintain the canonical consolidation specs; archive old specs; delete `docs/` | ✅ Complete |
| **1 — RED tests** | Create `packages/swarm/` skeleton; write all `tests/swarm/` tests; confirm 100% fail | Next step |
| **2 — GREEN + REFACTOR** | Implement each module (Red→Green→Refactor per module); delete old tests after each module's refactor | |
| **3 — Cutover** | Delete dead code; delete old packages; confirm only `tests/swarm/` remains | |

Start a fresh context window for Phase 1 onwards to avoid context exhaustion mid-implementation.

## Cross-references

The full inventory and dependency map is above (see "Spec inventory and reading paths"). This list is annotated quick access to the most-cited specs from this overview:

**Optional follow-up:**

- `01-package-structure.md` — flat file layout and import rules
- `04-swarm-api.md` — Hello World and Swarm + AgentSpec reference
- `08-test-strategy.md` — Red → Green → Refactor discipline
- `09-test-map.md` — every old test file mapped to new equivalent or deletion reason
- `12-token-budget.md` — token counting APIs, context overhead baseline, output estimation heuristics, model selection by context window
- `13-run-logger.md` — run-level capture, `RunReport`, and evaluation persistence

**Historical source:**

- `14-deferred-features.md` — archived spec families that remain deferred or historical

---

## Distribution and documentation

### Audience split

The docs site has two distinct audiences with separate entry paths:

- **Adopters** — teams building a product that uses `pyarnes_swarm` as a runtime dependency. They need to know which symbols are stable, how to scaffold a project with Copier, and how to wire the three-part contract (register tools → compose guardrails → run the loop). They should never need to read the API reference to scaffold their first working CLI.
- **Contributors** — engineers evolving `pyarnes_swarm` itself. They need to know the semver policy, how to add a new `Guardrail` or `Scorer` without breaking downstream pins, and how to evolve the Copier template safely.

### `docs/getting-started/distribution.md`

The canonical adopter onboarding page. Covers:

- The distribution recommendation in one sentence: library-first, adopter owns the CLI, `pyarnes-tasks` is dev-only.
- The three-phase model: **bootstrap** (scaffold via Copier) → **develop** (write tools/guardrails, run `uv run tasks check`) → **run** (ship the adopter's own CLI).
- The full adopter/package inventory table showing which `pyarnes_swarm` symbol or sub-module enters at each phase.
- `pyarnes_ref` pinning strategy: default `main` for bleeding-edge; pin to a tag once the first stable release lands; bump via `uv sync` after updating `pyarnes_ref`.
- Cross-reference to `docs/template.md` for the full Copier walkthrough.

### `docs/architecture/meta-use.md`

The Adopter C (rtm-toggl-agile) pattern page. Covers:

- Why `pyarnes_swarm` appears twice in this shape: shipped runtime + dev-time coding-agent harness.
- Full hook code (imported from `template/.claude/hooks/` to stay in sync rather than duplicated).
- The lifecycle-per-branch pattern: each git branch gets its own `.pyarnes/` JSONL stream so parallel feature branches don't interleave audit logs.
- `.pyarnes/` directory layout (mirrors the layout in `06-hook-integration.md`).
- How the bench corpus is structured: `tests/bench/scenarios/*.yaml` labelled fixtures, `EvalSuite` + `DiffSimilarityScorer` / `TestsPassScorer`, minimum `pass_rate >= 0.80` assertion.
- Cross-reference to `tests/bench/test_agent_quality.py.jinja` from `06-hook-integration.md`.

### Semver policy discoverability

Semver policy lives in `01-package-structure.md` (stable API surface tables and breaking-change rules). The docs surface this through two entry points:

- `docs/getting-started/distribution.md` links to `docs/development/release.md` for adopters who want to understand the pinning contract.
- `docs/development/evolving.md` includes the "Stable API surface" section (full tables from `01-package-structure.md`) and the breaking-change policy for contributors.
