# Deep Dive: pyarnes_swarm — Consolidation Specs (Phase 0)

**Generated**: 2026-04-28  
**Phase**: Phase 0 — Specification (pre-implementation)  
**Files**: `specs/consolidation/00-overview.md` through `specs/consolidation/12-token-budget.md` (13 specs)

---

## Overview

### What This Designs

`pyarnes_swarm` is a consolidation of five separate Python packages (`pyarnes-core`, `pyarnes-harness`, `pyarnes-guardrails`, `pyarnes-bench`, `pyarnes-tasks`) into a single installable package. The specs define the target architecture, public API, test strategy, and operational constraints before a single line of implementation is written.

The package solves a specific gap: AI coding agents (Claude Code, Cursor, Codex) generate tool calls but have no built-in system for retrying failures, feeding errors back to the model, enforcing safety limits, or tracking how much a session costs.

### Why This Approach Was Chosen

The consolidation was driven by three compounding problems in the monorepo:

1. **Cross-package import friction** — users had to import from five namespaces to wire a basic agent loop. `pyarnes_harness` re-exported `GuardrailChain` from `pyarnes_guardrails` because users didn't think in five packages — they thought in one. Every re-export is a place for drift.

2. **Duplicated observability** — `core/observe/` (transport) and `core/observability/` (domain events) were two directories serving one concern. Six files → four files in one subpackage.

3. **Scattered public API** — the 80% "Hello World" use case required knowing which symbols lived in which of the five packages. After consolidation: `from pyarnes_swarm import Swarm, AgentRuntime, GuardrailChain`.

### Context

These are **design specs, not implementation**. They follow the principle: write tests before code (Red → Green → Refactor), which means writing specs before tests. The specs define what the tests must verify; the tests then enforce what the implementation must produce. Nothing is implemented until Phase 1.

---

## Spec Walkthrough

### Spec 00: Overview (`00-overview.md`)

**Purpose**: The "why" document. Explains the problem, goals, and the canonical loop diagram.

**Key insight — the canonical loop diagram**: Shows that `litellm.token_counter()` runs *before* every model call. This is the O(n²) cost problem made visible in a diagram:

```
AgentLoop.run()
    ├─► litellm.token_counter(messages)     ← measure BEFORE calling the model
    │        │ >= 75% threshold → MessageCompactor.compact()
    │        │ >= Budget.max_tokens → stop
    │        ▼
    ├─► ModelClient.next_action()           ← only called if context fits
```

**Why the diagram lives in the overview**: It's the single most important thing to understand about the system. Every other design decision flows from it.

---

### Spec 01: Package Structure (`01-package-structure.md`)

**Purpose**: Defines the 18-file flat layout and the layer rules.

**Key insight — the layer rules**:

```
contracts  (ports.py, errors.py)   → stdlib only
domain                              → contracts
adapters                            → contracts + domain
infrastructure                      → contracts
__init__.py                         → all
```

A violation of these rules (e.g. `agent.py` importing from `bus.py`) is a bug, not a style issue. The layers exist so that the contracts stay stable even when adapters change.

**Key insight — one Protocols file**:
All Protocols (`ToolHandler`, `ModelClientPort`, `MessageBus`, `ModelRouter`, `GuardrailPort`, `SecretStore`) live in a single `ports.py`. Why? Because when you need to implement a custom backend, you only need to read one file to understand every contract in the system.

**Key decision — Guardrail ABC vs GuardrailPort**:
- `GuardrailPort` (in `ports.py`) is the injection Protocol — used by `Swarm` to accept the chain
- `Guardrail` (in `guardrails.py`) is the ABC callers subclass when writing a custom guardrail

This mirrors how Python's `collections.abc` separates the Protocol (what the runtime checks) from the ABC (what you inherit from when you want the framework's defaults).

---

### Spec 02: MessageBus (`02-message-bus.md`)

**Purpose**: Defines how agents running as separate OS processes communicate.

**Why separate OS processes?**: Python's GIL (Global Interpreter Lock) prevents true parallelism in threads. Two agents sharing a process also share memory — a crash in one can corrupt the other's state. Separate processes avoid both. The downside: they can't share in-process queues, so a `MessageBus` is needed.

**Three bus implementations** — each answers a different question:

| Bus | Answers | Trade-off |
|---|---|---|
| `InMemoryBus` | "How do I test this without infrastructure?" | No persistence, single-process only |
| `TursoMessageBus` | "How do I run locally with no infra?" | BETA, MVCC SQLite rewrite (Limbo/Turso) |
| `NatsJetStreamBus` | "How do I run in production at scale?" | Requires a NATS server |

**Why Turso/Limbo over standard SQLite?**: Standard SQLite has WAL mode for concurrent reads, but only one writer at a time. Limbo (Turso's Rust rewrite) uses MVCC (Multi-Version Concurrency Control) — multiple writers from multiple OS processes without serialization. This is the same technique PostgreSQL uses.

---

### Spec 03: ModelRouter (`03-model-router.md`)

**Purpose**: Defines how the swarm selects which model handles each task.

**The core problem**: Running every task on the most capable (most expensive) model is wasteful. A task that asks "what is 2+2?" doesn't need Claude Opus.

**Two router implementations**:

#### `RuleBasedRouter` — static rules
```python
router = RuleBasedRouter([
    RoutingRule(max_tools=2, max_complexity=0.3, model="claude-haiku-4-5"),
    RoutingRule(max_tools=6, max_complexity=0.7, model="claude-sonnet-4-6"),
    RoutingRule(model="claude-opus-4-7"),  # catch-all
])
```
First matching rule wins. Simple, predictable, zero overhead.

#### `LLMCostRouter` — cost-aware with context window filtering
Selection happens in three steps:
1. **Context window filter** — exclude models whose `max_tokens < required_context_tokens`. A task requiring 150K tokens of context cannot go to a model with a 100K window.
2. **Complexity filter** — select the tier whose `max_complexity >= task.complexity_score`.
3. **Cost sort** — within the matching tier, pick the cheapest model by `litellm.model_cost`.

**Why the context window filter matters**: Without it, the router might pick a cheap model, the request would fail or truncate silently, and the error would be opaque. Explicit pre-flight filtering makes the failure mode `UserFixableError("No model fits context")` — actionable.

**The efficiency feedback loop**:
```
Scorer → EvalResult(score, cost) → suite.cost_efficiency → router.observe()
```
After enough eval runs, cheap models that consistently score well on a task type get promoted. This closes the loop between evaluation and routing.

---

### Spec 04: Swarm API (`04-swarm-api.md`)

**Purpose**: The "Hello World" spec. Defines the public-facing API.

**Five-step Hello World**:
1. Define a `ToolHandler`
2. Register it in a `ToolRegistry`
3. Compose `GuardrailChain`
4. Build a `Swarm` with `AgentSpec`
5. Call `swarm.run_agent()`

This is the 80% use case. Everything else (Budget, ProviderConfig, MessageCompactor) is advanced/optional.

**`run_parallel()` contract**:
```python
async def run_parallel(
    self,
    tasks: list[tuple[str, list[dict]]],  # (agent_name, messages) pairs
    *,
    max_concurrency: int = 4,
    timeout: float | None = None,
) -> list[list[dict] | Exception]: ...
```
The result list is **always the same length and order as the input** — even if some tasks fail. Failed tasks get the `Exception` object in their slot, not a missing value. This is the correct API shape for parallel work: partial failure should be visible, not silently swallowed.

**`MessageCompactorConfig`** — the context cost control:
```python
@dataclass(frozen=True)
class MessageCompactorConfig:
    context_window: int
    capacity_threshold: float = 0.75
    summary_max_tokens: int = 512
    overhead_tokens: int = 0    # measured once at startup via acount_tokens()
    output_reserve: int = 4096  # reserved for model output
```
`overhead_tokens` is the most important field: it accounts for `CLAUDE.md`, MCP server configs, and tool schemas that are always in the context but don't change. Measuring them once at startup (via `acount_tokens()`) prevents the "context budget shrinks mid-session" surprise.

---

### Spec 05: Dead Code Audit (`05-dead-code-audit.md`)

**Purpose**: Documents what gets deleted and why.

**What was cut**:

| What | Why |
|---|---|
| `SeccompSandbox` | Linux-only, zero callers outside the package |
| `SWEBenchScenario` | "Execution deferred to a future milestone" — never implemented |
| `_HasScore` Protocol | Vulture-confirmed unused; replaced by direct attribute access |
| `harness/guardrails.py` | Pure re-export shim; dissolves when packages merge |

**Design principle revealed**: The audit uses three passes — vulture (automated dead code detection), callee analysis (manual tracing), and cognitive complexity scan (naming that suggests duplication). The naming scan is the most important: any two class names that differ only by a suffix (`-er`, `-or`, `-Transformer`, `-Compressor`) are a red flag for one concept split across two files.

**`Budget` vs `IterationBudget` — NOT merged (this is the key "don't merge" decision)**:
- `Budget` — immutable, `frozen=True`, returns a *new* instance on `consume()`. Used by Claude Code Stop hooks to record what was spent.
- `IterationBudget` — mutable, `asyncio.Lock`-protected, shared across parent and sub-agents in a swarm. Has `refund()`.

These look similar but serve completely different purposes. Merging them would produce a class that is simultaneously a value type (immutable) and a shared mutable counter — which is a contradiction.

---

### Spec 06: Hook Integration (`06-hook-integration.md`)

**Purpose**: Shows how `pyarnes_swarm` integrates with Claude Code's hook system.

**The "meta-use" pattern**: `pyarnes_swarm` is imported *twice* in a project:
1. By the agent's own tools (the thing being built)
2. By the Claude Code hooks that govern the coding agent building those tools

This is unusual. Most libraries are used in one direction. Here, `pyarnes_swarm` is the tool AND the safety layer around the tool.

**Three hook points**:

| Hook | `pyarnes_swarm` primitive |
|---|---|
| `PreToolUse` | `GuardrailChain.check()` — blocks forbidden tool calls |
| `PostToolUse` | `ToolCallLogger.log_call()` — audit trail |
| `Stop` | `Budget.allows()` — hard-stop sessions exceeding spend cap |

**Budget exhaustion pattern**:
```python
allowed = await budget.consume()
if not allowed:
    break   # clean stop, not an exception
```
`consume()` returns `False` without raising — the caller decides whether exhaustion is an error. This is correct for cooperative systems: an exception would unwind the stack and lose work in progress; a `False` return lets the agent finish its current action cleanly.

---

### Spec 07: Bench — Integrated Axes (`07-bench-integrated-axes.md`)

**Purpose**: Redesigns the scorer to connect quality, cost, and routing.

**The gap before redesign**:
```
Scorer.score() → float only      ← no usage info, no cost
BurnTracker    → separate call   ← manually joined by callers
EvalResult     → usage/cost always None unless caller populates them
```

**The fix — `ScoreResult`**:
```python
@dataclass(frozen=True)
class ScoreResult:
    score: float
    usage: TokenUsage | None = None  # tokens the scorer itself spent (e.g. judge call)
    passed: bool | None = None
```

**Breaking change**: `Scorer.score()` now returns `ScoreResult`, not `float`. All existing scorer subclasses must be updated.

**Why return token usage from the scorer?**: An `LLMJudgeScorer` makes its own LLM call to evaluate quality. That call has a cost. If you don't capture it, you're measuring "how much did the agent cost?" but ignoring "how much did the evaluation cost?" — which leads to false economy (cheap evaluation that misses bugs is more expensive in the long run than slightly pricier accurate evaluation).

**`EvalSuite.run()` as the integration point**: joins agent token usage + scorer token usage + cost calculation. The caller no longer plumbs these together manually.

---

### Spec 08: Test Strategy (`08-test-strategy.md`)

**Purpose**: Declares the discipline: Red → Green → Refactor.

**The rule that prevents parallel test suites**:
> Old tests for a module are deleted immediately after refactor. Never keep both old and new tests running simultaneously.

Why? Two test suites for the same module are not "extra safety" — they're conflicting specifications. When one passes and the other fails, you don't know which one is correct. Deleting old tests after the new suite is green eliminates the ambiguity.

**The "covers its intent" rule**: Before deleting an old test, verify the new test covers the *intent*, not just the *code path*. A test that exists to verify "the error message says X" covers different intent than a test that verifies "the error is catchable by callers as `TransientError`".

---

### Spec 09: Test Map (`09-test-map.md`)

**Purpose**: Maps every existing test file to its replacement or deletion reason.

**Key pattern — three categories**:
- **MIGRATE** (~55 files): content ports to a new file in `tests/swarm/`
- **DELETE** (~10 files): test was for dead code or docs that no longer exist
- **KEEP** (~25 files): test belongs to `bench/`, `template/`, or `tasks/` which are not being consolidated

**New surface tests** (no old equivalent):
- `test_providers.py` — `ModelClient` with mocked LiteLLM
- `test_secrets.py` — `ChainedSecretStore` fallback ordering
- `test_routing.py` — `LLMCostRouter` with mocked `model_cost`
- `test_bus.py` — `InMemoryBus`, `TursoMessageBus` with `:memory:`
- `test_swarm.py` — end-to-end `Swarm.run_parallel()` result ordering
- `test_token_budget.py` — `MessageCompactor` trigger logic, context window filter

---

### Spec 10: Provider Config (`10-provider-config.md`)

**Purpose**: Defines how `ModelClient` connects to different provider APIs.

**`ProviderConfig`** binds a model client to a specific provider:
```python
@dataclass(frozen=True)
class ProviderConfig:
    provider_type: str    # "anthropic", "openrouter", "huggingface", "nvidia_nim"
    api_key_name: str     # key name in SecretStore (e.g. "openrouter")
    base_url: str | None = None  # override endpoint (required for NIM self-hosted)
```

**Why not hardcode provider names in `ModelClient`?**: Because `ModelClient` uses LiteLLM's unified API — the provider prefix in the model ID (`openrouter/anthropic/claude-3-haiku`) is enough for routing. `ProviderConfig` only adds the secret resolution step: which key in the `SecretStore` holds the API key for this provider.

---

### Spec 11: Secrets Management (`11-secrets.md`)

**Purpose**: Explains why `.env` files are unsafe and what to use instead.

**`.env` failure modes** (the case against them):
1. `.gitignore` entry forgotten after `git init`
2. `.gitignore` accidentally removed in conflict resolution
3. `git add -f` bypasses `.gitignore` silently
4. Shared laptops with developer `.env` baked into Docker images
5. Backup tools that archive the workspace including `.env`

**The solution — `keyring` library** (used by `pip`, `twine`, `Jupyter`):
- macOS → Keychain Access (system-level AES-256, locked to user)
- Windows → Windows Credential Manager (DPAPI-encrypted)
- Linux → libsecret / GNOME Keyring or KWallet
- Linux headless → no daemon → falls back to `EnvSecretStore`

**Why `keyring`, not a bespoke encrypted file?**: Rolling your own encryption means rolling your own key management. Where does the decryption key live? Usually in another file, or hardcoded, or derived from a password — each of which reintroduces the original problem. `keyring` delegates key management to the OS, which has hardware-backed key stores on modern hardware.

**`ChainedSecretStore`** — the recommended default:
```python
store = ChainedSecretStore(
    KeyringSecretStore(namespace="pyarnes"),  # works locally
    EnvSecretStore(prefix="PYARNES_"),        # works in CI
)
```
Same code path in both environments. `KeyringSecretStore` fails fast on headless systems (no daemon); `ChainedSecretStore` silently falls through to the env var fallback.

**`LiteLLMModelClient` always calls `store.get()`, not `store.get_optional()`**: Missing keys fail immediately with `KeyError`, not silently with a `None` API key that produces a cryptic 401 error later.

---

### Spec 12: Token Budget Management (`12-token-budget.md`)

**Purpose**: Addresses the super-linear cost problem in agentic loops.

**The O(n²) cost problem**:
```
Iteration 1:  1 000 tokens
Iteration 2:  2 000 tokens  (full history resent)
Iteration 10: 10 000 tokens
Total: 1+2+…+10 = 55× the cost of one iteration
```

**Three control layers**:

| Layer | Mechanism | When measured |
|---|---|---|
| System overhead baseline | `acount_tokens()` — API-accurate | Once at startup |
| Per-request compaction | `token_counter()` — local, fast | Every loop iteration |
| Session token cap | `Budget.max_tokens` | Every loop iteration |

**Why two different token counting functions?**
- `acount_tokens()` calls the provider's API and is accurate (accounts for Anthropic's internal system token additions). Use it once at startup to measure CLAUDE.md + MCP configs + tool schemas.
- `token_counter()` uses a local tokenizer approximation. It's fast and free. Use it inside the hot loop where you call it on every iteration.

**Output token estimation — the unsolved problem**: No library can predict output token count before a call. The spec provides heuristics:

| Task type | Heuristic |
|---|---|
| Short factual answer | 256 tokens (constant) |
| Structured JSON | 1.4 × schema token count |
| Tool-call sequence | 3 × input tokens |
| Chain-of-thought | 5 × input tokens |
| Code generation | 2 × input tokens |

After enough runs, replace these with P95 values from `BurnTracker` histograms.

**TALE technique** (Token-Budget-Aware LLM Reasoning, ACL 2025): Ask the model to self-estimate its output budget via a zero-shot prompt before the real call. Achieves ~67% output token reduction on reasoning tasks. One extra cheap model call — only worthwhile for planning/complex reasoning where output length is unpredictable.

**Model tier recommendations for system tasks**:
- Compaction summariser → cheapest tier (Haiku-class)
- TALE self-estimator → cheapest tier (single-integer output)
- Task planning → most capable tier (Opus-class)
- Simple tool execution → cheapest tier

---

## Concepts Explained

### Design Patterns Used

| Pattern | Where | Why |
|---|---|---|
| Ports & Adapters (Hexagonal) | `ports.py` + all adapters | Contracts stay stable when infra changes |
| Protocol (structural typing) | All Ports | No inheritance required; structural check at type-check time |
| ABC (abstract base class) | `Guardrail`, `Scorer` | Provides default behaviour + enforces `@abstractmethod` |
| Strategy | `ModelRouter` implementations | Swap routing logic without changing the loop |
| Chain of Responsibility | `GuardrailChain` | Each guardrail checks independently; first violation wins |
| Observer | `LLMCostRouter.observe()` | Routing learns from evaluation results |
| Immutable value object | `Budget`, `TaskMeta`, `ScoreResult` | `frozen=True` prevents accidental mutation across goroutines |
| Mutable shared resource | `IterationBudget` | `asyncio.Lock` makes concurrent consume/refund safe |

---

### Key Technical Concepts

#### Ports & Adapters (Hexagonal Architecture)

**What**: Separate the core business logic (domain) from the infrastructure (databases, APIs, queues) by defining *Protocols* (ports) that the infrastructure must satisfy.

**Why Used Here**: The swarm needs to work with any LLM provider, any message bus, and any secret store. If `AgentLoop` directly called `litellm.completion()`, swapping to a different provider would require editing the loop. With `ModelClientPort`, the loop only knows the Protocol — any implementation that satisfies `async def next_action(messages) -> dict` works.

**When to Use**: When you anticipate swapping infrastructure (provider, database, queue) without changing business logic. When you want to inject fakes in tests without patching.

**Trade-offs**:
- Pros: testable without real infrastructure; providers become pluggable
- Cons: one extra indirection layer; Protocol errors only caught at type-check time

**Alternatives**:
- Direct coupling: simpler, but locks you to one provider
- Abstract factory: heavier; adds factory classes that `Protocol` doesn't need

---

#### Structural Typing (Protocol)

**What**: Python's `typing.Protocol` defines an interface by structure, not inheritance. Any class with the right method signatures satisfies the Protocol — no `class MyBus(MessageBus)` required.

**Why Used Here**: Forces callers to implement only the methods the system actually needs. A `MessageBus` that only needs `publish` shouldn't be forced to implement `subscribe` and `resume_from` just to satisfy an ABC.

**When to Use**: When you want duck typing with type-checker enforcement. When the implementer is in a different codebase and inheritance would create a dependency.

**Example**:
```python
class MessageBus(Protocol):
    async def publish(self, topic: str, payload: bytes) -> None: ...

class MyRedisAdapter:  # no inheritance needed
    async def publish(self, topic: str, payload: bytes) -> None:
        await redis.publish(topic, payload)
```

---

#### MVCC (Multi-Version Concurrency Control)

**What**: A database concurrency mechanism where writers create new versions of rows instead of locking them. Readers always see a consistent snapshot; writers don't block readers.

**Why Used Here**: `TursoMessageBus` needs multiple agent OS processes to write messages simultaneously. Standard SQLite allows only one writer at a time (WAL mode still serializes writers). Turso/Limbo uses MVCC so agent-1 publishing `"task.start"` doesn't block agent-2 publishing `"task.progress"`.

**When to Use**: Any scenario with concurrent writes and need for consistent reads. PostgreSQL, CockroachDB, and FoundationDB all use MVCC.

---

#### O(n²) Token Cost in Agentic Loops

**What**: Each LLM call in an agentic loop sends the full message history. After n iterations, iteration k sends k × (average message size) tokens. Total tokens = 1 + 2 + … + n = n(n+1)/2 = O(n²).

**Why it matters**: At 10 iterations with 1 000-token average history, you've sent 55 000 tokens — 5.5× what you'd expect if you assumed linear growth. At 50 iterations: 1 275 000 tokens (127× iteration 1).

**The fix — compaction**: Summarise old messages periodically. The context stays bounded; cost stays O(n × summary_size) instead of O(n²).

**The metric — capacity_threshold**: Compact when `current_tokens / context_window >= 0.75`. The 25% headroom accommodates: model output tokens, tokenizer approximation error (5–10%), and internal system tokens the provider adds for tool use.

---

#### Cost-Aware Routing

**What**: Choosing the cheapest model that can handle a task's complexity, rather than always using the most capable model.

**Why Used Here**: In a multi-agent swarm running hundreds of iterations, model cost is the dominant operational expense. A task with `complexity_score=0.2` does not benefit from a Opus-class model — the quality improvement is negligible; the cost difference is 10–20×.

**The feedback loop**: `LLMCostRouter.observe(model_id, task_type, efficiency)` adjusts internal weights after eval runs. This is a lightweight Bayesian update — not gradient descent. It does not require an ML pipeline or external service.

---

## Learning Resources

### Official Documentation

- [LiteLLM Token Counting](https://docs.litellm.ai/docs/count_tokens): `token_counter`, `acount_tokens`, `get_max_tokens` — the three measurement primitives
- [Anthropic Token Counting API](https://platform.claude.com/docs/en/build-with-claude/token-counting): `count_tokens()` endpoint, system prompt overhead, tool schemas
- [Python `typing.Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol): structural subtyping, `@runtime_checkable`, how it differs from ABC
- [keyring library](https://keyring.readthedocs.io/): OS keychain integration, backends per platform, headless fallback
- [asyncio Synchronisation Primitives](https://docs.python.org/3/library/asyncio-sync.html): `asyncio.Lock` — used in `IterationBudget.consume()`

### Tutorials & Articles

- [Hexagonal Architecture (Ports and Adapters)](https://alistair.cockburn.us/hexagonal-architecture/): The original 2005 paper by Alistair Cockburn — explains why you always end up re-implementing the pattern when you don't name it
- [MVCC Explained](https://www.postgresql.org/docs/current/mvcc-intro.html): PostgreSQL docs on MVCC — the same concept used by Turso/Limbo
- [Python Structural Subtyping](https://peps.python.org/pep-0544/): PEP 544 — the proposal that added `Protocol` to Python; explains why it's safer than duck typing without it
- [Cost of LLM API Calls](https://simonwillison.net/2023/May/18/the-architecture-of-todays-llm-applications/): Simon Willison on token costs — good context for why routing and compaction matter

### Videos

- [Hexagonal Architecture in Python](https://www.youtube.com/watch?v=C7MRkqP5N10): Practical implementation walkthrough, ~45 min
- [asyncio Deep Dive](https://www.youtube.com/watch?v=Xbl7XjFYsN4): Understanding event loops, tasks, and locks — prerequisite for understanding `IterationBudget`

### Research Papers

- [TALE: Token-Budget-Aware LLM Reasoning (arXiv:2412.18547)](https://arxiv.org/abs/2412.18547): The self-estimation technique referenced in spec 12; shows how asking a model to estimate its own output budget reduces token use by ~67% on reasoning tasks

### Related Concepts (For Deeper Study)

- **Event Sourcing**: The `MessageBus.resume_from(topic, offset)` pattern is event sourcing — replay from a known offset. Understanding event sourcing explains why `offset` exists.
- **Semaphore vs Lock**: `run_parallel()` uses a semaphore (`max_concurrency`) not a lock. A semaphore allows N concurrent holders; a lock allows exactly 1.
- **Structural Pattern Matching**: Python 3.10+ `match` statement is useful for dispatching on `ActionKind` (tool_call vs final_answer) — the pattern `AgentLoop` uses internally.
- **Bayesian Updating**: The `LLMCostRouter.observe()` efficiency feedback is a simplified Bayesian update — prior routing weights updated by new evidence (eval results). No ML framework required for this.

---

## Related Code in This Project

| File | Relationship |
|---|---|
| `specs/consolidation/00-overview.md` | Entry point — read first; has the canonical loop diagram |
| `specs/consolidation/01-package-structure.md` | Layer rules + all Protocol definitions in `ports.py` |
| `specs/consolidation/04-swarm-api.md` | Public API — the Hello World; where most users start |
| `specs/consolidation/08-test-strategy.md` | How to write tests; Red→Green→Refactor rules |
| `specs/consolidation/09-test-map.md` | Every test file mapped; the implementation checklist for Phase 1 |
| `specs/consolidation/12-token-budget.md` | Token counting deep-dive; read before implementing `MessageCompactor` |
| `specs/archive/` | 11 implemented specs from the monorepo era; useful for understanding the history |
| `packages/core/src/pyarnes_core/` | Monorepo source that will be consolidated into `pyarnes_swarm` |
| `packages/harness/src/pyarnes_harness/` | `AgentLoop` lives here; the largest behaviour unit to port |

---

## Next Steps

1. **Try reading the loop diagram** (`00-overview.md`): Trace a single tool call through the diagram. At each arrow, ask "where does this code live?" — the answer maps to one of the 18 files in spec 01.

2. **Deeper dive — token budget**: If you're unfamiliar with the O(n²) cost problem, implement a toy agent loop that counts tokens on every iteration and prints the cumulative total. You'll see the growth rate immediately.

3. **Common pitfalls to watch for in Phase 1**:
   - Using `acount_tokens()` inside the hot loop instead of at startup — it's an API call; it will dominate latency
   - Testing `LLMCostRouter` without mocking `litellm.model_cost` — the table changes when LiteLLM releases updates; tests must pin it
   - Merging `Budget` and `IterationBudget` — they look similar but are fundamentally different (immutable value vs mutable shared counter)
   - Forgetting to delete old tests after refactor — two test suites for the same module create ambiguity, not safety

4. **Phase 1 starting point**: Read `specs/consolidation/09-test-map.md` for the full list of test files to create, then `specs/consolidation/08-test-strategy.md` for the Red→Green→Refactor discipline. Create `packages/swarm/` skeleton first — empty `__init__.py` so all tests fail cleanly with `ImportError` rather than `NameError`.

---

*This deep dive was generated by AntiVibe - the anti-vibecoding learning framework.*  
*Learn what AI writes, not just accept it.*
