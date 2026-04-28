# pyarnes_swarm — Consolidation Overview

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
    │        │ violation → UserFixableError (bubble up to human)
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

## Consolidation sequence (do in order)

Each phase must complete before the next begins. Do not run phases in parallel.

| Phase | What happens | When done |
|---|---|---|
| **0 — Specs** | Write 11 consolidation specs; archive old specs; delete `docs/` | ✅ Complete |
| **1 — RED tests** | Create `packages/swarm/` skeleton; write all `tests/swarm/` tests; confirm 100% fail | Next step |
| **2 — GREEN + REFACTOR** | Implement each module (Red→Green→Refactor per module); delete old tests after each module's refactor | |
| **3 — Cutover** | Delete dead code; delete old packages; confirm only `tests/swarm/` remains | |

Start a fresh context window for Phase 1 onwards to avoid context exhaustion mid-implementation.

## See also

- `01-package-structure.md` — flat file layout and import rules
- `04-swarm-api.md` — Hello World and Swarm + AgentSpec reference
- `08-test-strategy.md` — Red → Green → Refactor discipline
- `09-test-map.md` — every old test file mapped to new equivalent or deletion reason
- `12-token-budget.md` — token counting APIs, context overhead baseline, output estimation heuristics, model selection by context window
