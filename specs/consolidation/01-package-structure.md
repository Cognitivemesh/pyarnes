# pyarnes_swarm — Package Structure

> **Spec header**
>
> | Field | Value |
> |---|---|
> | **Title** | pyarnes_swarm — Package Structure |
> | **Status** | active |
> | **Type** | core-runtime |
> | **Tags** | architecture, packaging, imports |
> | **Owns** | package boundaries, layer rules, ports.py contracts (TaskMeta, ModelClientPort, ToolHandler), errors.py taxonomy, semver-stable __init__ surface, file/folder architecture |
> | **Depends on** | 00-overview.md |
> | **Extends** | — |
> | **Supersedes** | — |
> | **Read after** | 00-overview.md |
> | **Read before** | 02-test-strategy.md |
> | **Not owned here** | runtime loop sequence and recovery semantics (see `07-swarm-api.md`); evaluation contracts (see `15-bench-integrated-axes.md`); hook integration (see `10-hook-integration.md`, `09-loop-hooks.md`); transport adapters (see `12-transport.md`) |
> | **Last reviewed** | 2026-04-29 |

## Design Rationale

**Why a single `ports.py` for all Protocols?** When you need to implement a custom backend (model, bus, router), you read one file to understand every contract in the system. Spreading Protocols across files forces readers to hunt — and creates the temptation to define slightly incompatible versions of the same interface in different places.

**Why `ModelClientPort` (Protocol) and `Guardrail` (ABC) instead of one or the other?**
- `ModelClientPort` uses structural typing (`Protocol`) because model implementations often live in different codebases and inheritance would create a cross-package dependency.
- `Guardrail` uses an ABC because it provides useful default behaviour (violation logging) that inheritors get for free. A Protocol can't provide defaults.

**Why 18 flat files instead of deep subpackage nesting?** Each file has one clear purpose. If you want to understand routing, read `routing.py` — you don't need to navigate `core/routing/impl/strategies/llm_cost.py`. Flat layouts also mean shorter import paths, which are harder to accidentally break.

**Why is a layer violation a bug, not a style issue?** If `agent.py` imports from `bus.py` (an adapter), then changing the bus implementation requires reading and potentially changing the agent. The whole point of the layer boundary is that domain logic should not know about infra choices. A linter or import checker should catch these violations in CI.

## Specification

> **Diagram:** [Package architecture playground](diagrams/01-package-structure.html). Interactive map of the five packages (core · guardrails · harness · bench · tasks), with layer toggles, connection-type filters (dependency · data-flow · tool-call · event · skill-invoke), and click-to-comment on any module.

### Flat layout (18 top-level files + bench/ subpackage)

```bash
packages/swarm/
├── pyproject.toml
└── src/
    └── pyarnes_swarm/
        │
        │  ── CONTRACTS (no imports from other layers) ─────────
        ├── ports.py          # ALL Protocols in one file
        ├── errors.py         # All error types + Severity
        │
        │  ── DOMAIN (orchestration — imports only from contracts) ─
        ├── swarm.py          # Swarm, AgentSpec, TaskMeta
        ├── routing.py        # RuleBasedRouter, LLMCostRouter, RoutingRule, ModelTier
        ├── agent.py          # AgentLoop, AgentRuntime, LoopConfig, ModelClient
        │                     #   ModelClient: LiteLLM-backed, text/image/audio/embeddings
        │                     #   inlines: ClassifiedError, ActionKind, RetryPolicy
        ├── budget.py         # Budget (immutable) + IterationBudget (mutable async)
        ├── context.py        # AgentContext, Lifecycle, Phase FSM
        ├── tools.py          # ToolRegistry + @tool decorator
        ├── verification.py   # VerificationLoop, VerificationResult
        │
        │  ── ADAPTERS (concrete infra — imports domain + contracts) ─
        ├── bus.py            # TursoMessageBus [DEFAULT, BETA] + InMemoryBus
        ├── bus_nats.py       # NatsJetStreamBus (only importable with [nats] extra)
        ├── guardrails.py     # Guardrail ABC (inherit to write a guardrail) +
│                     #   GuardrailChain + all built-in guardrail classes
│                     # Note: !!! note "GuardrailPort vs. Guardrail"
    GuardrailPort (in ports.py) is the injection Protocol —
│                     #   used by Swarm to accept the chain; Guardrail is the ABC callers subclass
        │
        │  ── INFRASTRUCTURE (I/O helpers — no domain logic) ────
        ├── safety.py         # paths, injection, redact, sanitize, command_scan,
        │                     #   arg_walker, semantic_judge
        ├── observability/    # 4 files replacing 6+ across observe/ + observability/
        │   ├── __init__.py
        │   ├── transport.py  # loguru setup, configure_logging, get_logger, ContextVar
        │   ├── atoms.py      # iso_now, start_timer, monotonic_duration, dumps, to_jsonable
        │   ├── events.py     # log_event, log_warning, log_error,
        │   │                 #   log_lifecycle_transition, log_tool_call,
        │   │                 #   log_guardrail_violation
        │   └── telemetry.py  # configure_tracing, session_span ([otel] extra)
        ├── capture.py        # CapturedOutput, ToolCallLogger, cc_session
        ├── atomic_write.py   # write_private, append_private (0o600)
        ├── secrets.py        # SecretStore, KeyringSecretStore, EnvSecretStore,
        │                     #   ChainedSecretStore, ProviderConfig
        │
        │  ── ENTRY POINT ──────────────────────────────────────
        ├── __init__.py       # ~10 public symbols
        │
        │  ── OPTIONAL EXTRA ([bench]) ───────────────────────
        └── bench/
            ├── __init__.py
            ├── eval.py
            ├── scorers.py    # ScoreResult + ALL scorer classes (merged scorer.py + scorers.py)
            ├── fact.py
            ├── race.py
            ├── regression.py
            └── burn/
                ├── __init__.py
                ├── types.py
                ├── provider.py
                ├── costing.py
                ├── claude_code.py
                ├── classify.py
                ├── dedupe.py
                ├── normalize.py
                ├── kpis.py
                ├── optimize.py
                └── compare.py
```

### Layer rules

Each layer may only import from layers above it in the list. Import from a lower layer is a bug.

| Layer | May import from |
|---|---|
| contracts (`ports.py`, `errors.py`) | stdlib only |
| domain | contracts |
| adapters | contracts, domain |
| infrastructure | contracts |
| `__init__.py` | all |
| `bench/` | contracts, domain, infrastructure |

### Public API (`__init__.py`) — 14 symbols

```python
from pyarnes_swarm.swarm      import Swarm, AgentSpec
from pyarnes_swarm.agent      import AgentRuntime, LoopConfig, ModelClient
from pyarnes_swarm.ports      import MessageBus, ModelClientPort, ModelRouter, ToolHandler
from pyarnes_swarm.routing    import RuleBasedRouter, LLMCostRouter, ModelTier
from pyarnes_swarm.bus        import InMemoryBus, TursoMessageBus
from pyarnes_swarm.guardrails import GuardrailChain
```

## Key concepts

### Ports & Adapters (Hexagonal Architecture)

**What**: Separate core business logic (domain) from infrastructure (databases, APIs, queues) by defining Protocols (ports) that the infrastructure must satisfy. Domain code only knows the Protocol — any implementation that satisfies the interface works.

**Why Used Here**: `AgentLoop` needs to work with any LLM provider, any message bus, and any secret store. If it directly called `litellm.completion()`, swapping providers would require editing the loop. With `ModelClientPort`, the loop only knows `async def next_action(messages) -> dict` — the provider is pluggable.

**When to Use**: When you anticipate swapping infrastructure without changing business logic. When you want to inject fakes in tests without patching.

**Trade-offs**:
- Pros: testable without real infrastructure; implementations are pluggable
- Cons: one extra indirection layer; Protocol violations only caught at type-check time, not runtime

**Alternatives**:
- Direct coupling: simpler, but locks you to one provider
- Abstract factory: heavier; adds factory classes that `Protocol` doesn't need

**Learning**: [Hexagonal Architecture (original paper)](https://alistair.cockburn.us/hexagonal-architecture/) by Alistair Cockburn (2005); [Hexagonal Architecture in Python](https://www.youtube.com/watch?v=C7MRkqP5N10) (~45 min walkthrough)

---

### Structural Typing (Protocol)

**What**: Python's `typing.Protocol` defines an interface by structure, not inheritance. Any class with the right method signatures satisfies the Protocol — no `class MyBus(MessageBus)` required.

**Why Used Here**: Lets implementers satisfy a contract without importing from `pyarnes_swarm`. A `MessageBus` adapter in a separate codebase doesn't need to depend on this package to be compatible.

**When to Use**: When you want duck typing with type-checker enforcement. When the implementer is in a different codebase and inheritance would create a dependency.

**Example**:
```python
class MessageBus(Protocol):
    async def publish(self, topic: str, payload: bytes) -> None: ...

class MyRedisAdapter:  # no inheritance — satisfies MessageBus structurally
    async def publish(self, topic: str, payload: bytes) -> None:
        await redis.publish(topic, payload)
```

**Learning**: [PEP 544](https://peps.python.org/pep-0544/) — the proposal that added `Protocol` to Python; explains why it's safer than plain duck typing

```python
__all__ = [
    "Swarm", "AgentSpec",
    "AgentRuntime", "LoopConfig",
    # Concrete model adapter — LiteLLM-backed, supports text + image + audio + embeddings
    "ModelClient",
    # Ports (implement these to plug in custom backends)
    "ModelRouter", "MessageBus", "ModelClientPort", "ToolHandler",
    "RuleBasedRouter", "LLMCostRouter", "ModelTier",
    "InMemoryBus", "TursoMessageBus",
    "GuardrailChain",
]
```

Everything else is importable by path (`from pyarnes_swarm.budget import Budget`) but not part of the guaranteed public surface.

### Public API stability and semver

The guaranteed top-level public surface is exactly the set exported from `pyarnes_swarm.__init__`. Those symbols are the stable entry points adopters may depend on across minor releases.

Private and allowed to drift without notice:

- `_`-prefixed helpers
- internal module layout behind public imports
- JSON field ordering in capture logs
- log event names and structured telemetry keys
- concrete container types used behind public iterables
- the concrete type behind lifecycle-history storage

More explicitly:

- `ToolCallLogger` promises a stable set of fields for downstream readers, but not a stable field order in the JSONL output
- observability event names are internal telemetry, not part of the public API
- lifecycle/history iteration behavior may be stable while the backing container type is not

Semver expectations:

- MAJOR: removing or renaming a public symbol from `__init__`, changing a required method signature on a public ABC or Protocol, or changing the meaning of a persisted run/capture contract in a breaking way
- MINOR: adding new public symbols, new optional kwargs, new guardrail or scorer implementations, new optional sink/provider integrations
- PATCH: bug fixes, doc clarifications, private refactors, and internal file moves that preserve the public import surface

Anything importable only by deep path (`pyarnes_swarm.<module>`) but not re-exported from `__init__` is a documented implementation surface, not part of the strongest stability guarantee.

### `ports.py` — all Protocols in one file

```python
class ToolHandler(Protocol):
    async def execute(self, arguments: dict[str, Any]) -> Any: ...

class ModelClientPort(Protocol):
    """Implement this to plug in a custom model backend."""
    async def next_action(self, messages: list[dict[str, Any]]) -> dict[str, Any]: ...

class JudgeClient(Protocol):
    async def judge(self, prompt: str) -> str: ...

class MessageBus(Protocol):
    async def publish(self, topic: str, payload: bytes) -> None: ...
    async def subscribe(self, topic: str) -> AsyncIterator[bytes]: ...
    async def resume_from(self, topic: str, offset: int) -> AsyncIterator[bytes]: ...

class ModelRouter(Protocol):
    def route(self, spec: AgentSpec, meta: TaskMeta) -> str: ...

class SandboxHook(Protocol):
    async def run(self, code: str, timeout: float) -> str: ...

class GuardrailPort(Protocol):
    def check(self, tool_name: str, arguments: dict[str, Any]) -> None: ...

class LoggerPort(Protocol):
    def bind(self, **kwargs: Any) -> LoggerPort: ...
    def info(self, event: str) -> None: ...

class SecretStore(Protocol):
    def get(self, key: str) -> str: ...
    def get_optional(self, key: str) -> str | None: ...

class MessageTransformer(Protocol):
    async def __call__(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]: ...
```

`MessageTransformer` moves here from `harness/transform.py` (its only consumer is `compaction.py`, but the Protocol belongs with contracts). `TransformChain` stays in `agent.py` — it is an implementation, not a contract.

### `errors.py` — complete error taxonomy

```python
class TransientError(Exception):
    """Retry with exponential backoff (cap: 2)."""

class LLMRecoverableError(Exception):
    """Return as ToolMessage so the model adjusts."""

class UserFixableError(Exception):
    """Interrupt for human input."""

class UnexpectedError(Exception):
    """Bubble up for debugging."""

class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
```

`Severity` is kept in `errors.py` but removed from `__all__` — internal use only.

### Dependencies (`pyproject.toml`)

```toml
[project]
name = "pyarnes-swarm"
dependencies = [
    "pyturso>=0.1",     # TursoMessageBus (default MessageBus)
    "litellm>=1.0",     # LiteLLMModelClient + LLMCostRouter
    "keyring>=25.0",    # KeyringSecretStore (OS keychain)
    "loguru>=0.7",
    "libcst>=1.0",
]

[project.optional-dependencies]
nats  = ["nats-py>=2.6"]
otel  = ["opentelemetry-sdk>=1.20", "opentelemetry-exporter-otlp>=1.20"]
bench = ["pyarnes-swarm[otel]", "pydantic>=2.0"]
```

### What moved where

| Source (monorepo) | Destination |
|---|---|
| `core/dispatch/ports.py` + `core/types.py` | `ports.py` |
| `core/errors.py` | `errors.py` |
| `harness/loop.py` + `harness/runtime.py` | `agent.py` |
| `harness/classifier.py` | inlined into `agent.py` |
| `harness/transform.py` Protocol | `ports.py`; `TransformChain` → `agent.py` |
| `harness/compaction.py` + `harness/compressor.py` | `agent.py` (`MessageCompactor`) |
| `dispatch/action_kind.py` + `dispatch/retry_policy.py` | inlined into `agent.py` |
| `core/budget.py` + `harness/budget.py` | `budget.py` |
| `core/lifecycle.py` + context types | `context.py` |
| `harness/tools/` + `@tool` decorator | `tools.py` |
| `harness/verification.py` | `verification.py` |
| `guardrails/guardrails.py` | `guardrails.py` |
| `core/safety/` (all 7 modules) | `safety.py` |
| `core/observe/` + `core/observability/` | `observability/` (4 files) |
| `harness/capture/` | `capture.py` |
| `core/atomic_write.py` | `atomic_write.py` |
| `harness/routing.py` (new) | `routing.py` |
| `harness/bus.py` (new) | `bus.py` |
| `harness/bus_nats.py` (new) | `bus_nats.py` |
| `harness/secrets.py` (new) | `secrets.py` |
| `bench/` | `bench/` (mostly verbatim, scorers merged) |

### What was deleted

| Deleted | Reason |
|---|---|
| `core/sandbox.py::SeccompSandbox` | Linux-only, zero callers |
| `bench/swe_bench.py::SWEBenchScenario` | Pure stub, never implemented |
| `guardrails/benchmark_gate.py::_HasScore` | Vulture-confirmed unused |
| `core/observe/logger.py::CONSOLE` | Vulture-confirmed unused |
| `core/safety/semantic_judge.py::METADATA_DEPENDENCIES` | Vulture-confirmed unused |
| `harness/guardrails.py` | Pure re-export shim |
| `core/packaging/` | `version_of()` replaced by `__version__ = "0.1.0"` |
| `core/dispatch/ports.py` shim | Merged into `ports.py` |
| `core/types.py` shim | Merged into `ports.py` |

#### Layer Violations as CI-Checkable Bugs

To enforce the layered architecture, layer violations must be treated as explicit, CI-checkable bugs rather than just documentation guidelines. This is enforced using `ruff` rules:

```toml
[tool.ruff.lint.flake8-tidy-imports]
banned-module-level-imports = [
  "pyarnes.core.secrets", # Agent shouldn't know about secrets
  "pyarnes.harness.bus",  # Agent logic shouldn't depend on bus
]
```

Verify the layered architecture using:
```bash
uv run tasks lint --select=I901
```
