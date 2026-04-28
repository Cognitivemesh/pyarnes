# pyarnes_swarm — Swarm API

## Design Rationale

**Why five steps in the Hello World?** The five objects (`ToolHandler`, `ToolRegistry`, `GuardrailChain`, `Swarm`/`AgentSpec`) represent five genuinely different concerns: what tools do, where tools are registered, what safety rules apply, and how the swarm is composed. Collapsing them into fewer objects would mean either magic (auto-discovery) or a bloated constructor that accepts everything. The five steps are the minimum explicit wiring.

**Why does `run_parallel()` return `list[list[dict] | Exception]` instead of raising on failure?** In parallel workloads, partial failure is the common case — one agent failing should not cancel the others. Returning `Exception` objects in the result list means callers can inspect which tasks failed, retry only those, and keep successful results. An exception-based API would force callers to implement their own partial-failure logic, or lose all results when one fails.

**Why is `router=None` a `ValueError` if `AgentSpec.model` is also `None`?** Silent configuration errors are worse than loud ones. If you forget to specify a model and there's no router to pick one, the failure should happen at swarm construction time (before any tokens are spent), not mid-run with a cryptic `KeyError`.

**Why does `MessageCompactor` use `litellm.token_counter()` (local) in the loop and `acount_tokens()` (API) only at startup?** `acount_tokens()` makes a network call to the provider and takes ~100ms. Calling it on every loop iteration would add 100ms latency to every model call. `token_counter()` is a local computation taking microseconds. The tradeoff: slightly less accurate counts in the loop, but exact baseline measurement at startup where latency doesn't matter.

**Why does `run_parallel()` use a semaphore (`max_concurrency`) rather than a lock?** A semaphore allows N concurrent holders; a lock allows exactly 1. `run_parallel(max_concurrency=4)` lets 4 agents run simultaneously — a lock would serialise them entirely. `asyncio.Semaphore(max_concurrency)` is the correct primitive for bounding concurrency.

## Hello World (5-step minimum)

```python
import asyncio
from pathlib import Path
from pyarnes_swarm import (
    AgentRuntime, LoopConfig, ModelClient,
    GuardrailChain, Swarm, AgentSpec, InMemoryBus,
)
from pyarnes_swarm.guardrails import PathGuardrail
from pyarnes_swarm.tools import ToolRegistry
from pyarnes_swarm.ports import ToolHandler

# 1. Define a tool
class ReadFileTool(ToolHandler):
    async def execute(self, arguments: dict) -> str:
        return Path(arguments["path"]).read_text()

# 2. Register tools
registry = ToolRegistry()
registry.register("read_file", ReadFileTool())

# 3. Compose guardrails
guardrails = GuardrailChain([PathGuardrail(allowed_roots=("./workspace",))])

# 4. Build a swarm with one agent
swarm = Swarm(
    bus=InMemoryBus(),
    agents=[AgentSpec(
        name="my-agent",
        model="claude-haiku-4-5-20251001",
        tools=registry,
        guardrails=guardrails,
    )],
)

# 5. Run
result = asyncio.run(swarm.run_agent(
    agent="my-agent",
    messages=[{"role": "user", "content": "Read main.py and summarise it"}],
))
print(result[-1]["content"])
```

## `AgentSpec`

Declarative description of one agent in the swarm.

```python
@dataclass
class AgentSpec:
    name: str
    model: str | None = None          # None → router decides
    tools: ToolRegistry | None = None
    guardrails: GuardrailChain | None = None
    config: LoopConfig | None = None  # pass LoopConfig(budget=shared_budget) to wire IterationBudget
    complexity_hint: float = 0.5      # 0=trivial … 1=complex (for router)
    description: str = ""             # human-readable, used in routing logs
    log_path: Path | None = None      # if set, ToolCallLogger writes JSONL here
```

## `TaskMeta`

Defined in `swarm.py` alongside `Swarm` and `AgentSpec`. Also imported by `routing.py`. Computed from `AgentSpec` + task context before each run; the router uses this to select a model.

```python
@dataclass(frozen=True)
class TaskMeta:
    estimated_duration_seconds: float = 0.0
    tool_count: int = 0
    has_destructive_tools: bool = False
    complexity_score: float = 0.5
    model_hint: str | None = None
    required_context_tokens: int = 0   # overhead + history + output reserve; used by LLMCostRouter
                                        # to filter models whose context window is too small
```

## `Swarm`

```python
class Swarm:
    def __init__(
        self,
        bus: MessageBus,
        agents: list[AgentSpec],
        router: ModelRouter | None = None,   # None → use AgentSpec.model directly; raises ValueError if model is also None
        secret_store: SecretStore | None = None,
    ) -> None: ...

    async def run_agent(
        self,
        agent: str,                    # AgentSpec.name
        messages: list[dict],
        *,
        meta: TaskMeta | None = None,  # computed automatically if None
    ) -> list[dict]: ...

    async def run_parallel(
        self,
        tasks: list[tuple[str, list[dict]]],  # [(agent_name, messages), ...]
        *,
        max_concurrency: int = 4,
        timeout: float | None = None,          # per-task timeout in seconds; None = no limit
    ) -> list[list[dict] | Exception]: ...
```

`run_parallel` spawns each agent as a separate OS process and collects results via the `MessageBus`. Concurrency guarantees:

- At most `max_concurrency` agents run simultaneously (semaphore-controlled)
- If one agent raises an exception, the other agents continue; the failed task's slot in the result list contains the `Exception` object
- If `timeout` is set and a task exceeds it, the task is cancelled and a `TimeoutError` is placed in its result slot
- If a `router` is set, model selection happens per-task based on `TaskMeta`
- Results are returned in the same order as the input `tasks` list, regardless of completion order

## `LoopConfig`

Controls the loop's retry and iteration behaviour.

```python
@dataclass
class LoopConfig:
    max_iterations: int = 10       # max tool-call → result → next_action cycles
    max_retries: int = 2           # per TransientError
    budget: IterationBudget | None = None
    compaction_config: MessageCompactorConfig | None = None
    reflection_interval: int | None = None  # if None, reflection is disabled
```

Production checklist:
- Set `max_iterations` for worst-case task depth (default 10; raise for long chains)
- Set `max_retries` ≤ 2 (each retry = one LLM call on error)
- Wire `IterationBudget` for shared swarm step limits
- Set `LoopConfig.compaction_config` when running long sessions

## `MessageCompactorConfig` — context cost control

**The problem:** each loop iteration sends the full message history to the model. Cost grows super-linearly — 10 iterations with a 1 000-token average context costs 10× more than iteration 1 because the context is 10× longer by the end. Left unchecked this is O(n²) in token spend.

**The fix:** `MessageCompactor` measures context size before every model call using `litellm.token_counter()` (fast, local) and summarises old messages once the context exceeds a fraction of the effective window.

```python
@dataclass(frozen=True)
class MessageCompactorConfig:
    context_window: int               # model's max context window in tokens
    capacity_threshold: float = 0.75  # compact when tokens / effective_window >= this
    summary_max_tokens: int = 512     # max tokens for the compaction summary message
    overhead_tokens: int = 0          # fixed system overhead measured once at startup via acount_tokens()
    output_reserve: int = 4096        # reserved for model output; subtracted from available window
    # Effective window = context_window - overhead_tokens - output_reserve
```

`overhead_tokens` is measured **once at `Swarm` startup** using `litellm.acount_tokens()` (API-accurate), not on every loop iteration. `litellm.token_counter()` (local, zero-cost) is used inside the hot loop. See spec 12 for the full token budget system.

`MessageCompactor` calls `litellm.token_counter(model=model_id, messages=messages)` before every `ModelClient.next_action()` call. When `current_tokens / effective_window >= capacity_threshold`, it:

1. Summarises messages older than the most recent `N` tool-call pairs into a single `{"role": "system", "content": "<summary>"}` message
2. Replaces those messages in the history with the summary
3. The new context is small enough to continue safely

```python
# Wire it up:
LoopConfig(
    max_iterations=50,
    compaction_config=MessageCompactorConfig(
        context_window=200_000,   # claude-haiku-4-5-20251001
        capacity_threshold=0.75,  # compact at 150K tokens
        summary_max_tokens=512,
    ),
)
```

`litellm.token_counter()` is the single token measurement primitive. It handles tokenizer differences across providers — Anthropic, OpenAI, and open models each count tokens differently; LiteLLM normalises this. No separate tokenizer library is needed.

`Budget.max_tokens` (in `budget.py`) tracks **cumulative** token spend across the whole session and hard-stops the loop when the cap is hit. `MessageCompactorConfig` controls per-request context size. They address different failure modes and compose naturally.

## `AgentRuntime`

Lower-level entry point. Use when you want to manage a single loop without `Swarm`.

```python
runtime = AgentRuntime(
    model=ModelClient("claude-haiku-4-5-20251001"),
    tools=registry,
    guardrails=guardrails,
    config=LoopConfig(max_iterations=20),
)
result = await runtime.run([{"role": "user", "content": "..."}])
```

`Swarm.run_agent()` creates an `AgentRuntime` internally. Use `AgentRuntime` directly for single-agent setups or testing.

## Error handling

The four error types behave differently at the process boundary:

| Error | Default loop behaviour | What to do in production |
|---|---|---|
| `TransientError` | Retry up to `max_retries` | Log after final retry; emit a metric |
| `LLMRecoverableError` | Return as `ToolMessage` | Log if the model keeps triggering the same error |
| `UserFixableError` | Bubble up (loop stops) | Surface to UI or alert queue |
| `UnexpectedError` | Bubble up (loop stops) | Page on-call; attach `original` exception |

Wrap the entry point to handle the two bubble-up types distinctly:

```python
from pyarnes_swarm.errors import UnexpectedError, UserFixableError

try:
    result = await swarm.run_agent("my-agent", messages)
except UserFixableError as e:
    send_user_notification(str(e))
except UnexpectedError as e:
    alert_oncall(str(e))
    raise
```

## JSONL logging

Every tool call is logged by `ToolCallLogger`. Configure in `AgentSpec`:

```python
AgentSpec(
    name="my-agent",
    ...
    log_path=Path(".pyarnes/my_agent_tool_calls.jsonl"),
)
```

Each line:
```json
{"tool": "read_file", "arguments": {"path": "a.py"}, "result": "...",
 "is_error": false, "duration_seconds": 0.12, "started_at": "...", "finished_at": "..."}
```

## Observability

Configure logging at process start:

```python
from pyarnes_swarm.observability import configure_logging

configure_logging(level="INFO", fmt="json")   # production: JSONL to stderr
configure_logging(level="DEBUG", fmt="human") # development: readable
```

## Extending

### Custom tool handler

```python
from pyarnes_swarm.ports import ToolHandler

class SearchTool(ToolHandler):
    async def execute(self, arguments: dict) -> str:
        query = arguments["query"]
        return perform_search(query)

registry.register("search", SearchTool())
```

### Custom guardrail

```python
from pyarnes_swarm.guardrails import Guardrail, Violation
from pyarnes_swarm.errors import UserFixableError

class RateLimitGuardrail(Guardrail):
    def check(self, tool_name: str, arguments: dict) -> None:
        if self._is_over_limit(tool_name):
            raise UserFixableError(f"Rate limit exceeded for {tool_name}")
```

### Custom model client

Implement `ModelClientPort` (the Protocol) to use a backend other than LiteLLM:

```python
from pyarnes_swarm.ports import ModelClientPort

class MyModelClient:
    """Satisfies ModelClientPort — no subclassing needed (structural typing)."""
    async def next_action(self, messages: list[dict]) -> dict:
        # Call your LLM and return:
        # {"type": "tool_call", "tool": "...", "id": "...", "arguments": {...}}
        # {"type": "final_answer", "content": "..."}
        ...
```

Pass it wherever `ModelClientPort` is accepted (e.g. `AgentRuntime(model=MyModelClient(), ...)`).

## Self-registering `@tool` decorator (H10)

The `@tool` decorator registers a `ToolHandler` subclass in a module-level global registry without requiring the caller to build a `ToolRegistry` by hand.

```python
from pyarnes_swarm.tools import tool

@tool
class SearchTool(ToolHandler):
    """Registered automatically under the name 'searchtool' (class name lowercased)."""
    async def execute(self, arguments: dict) -> str: ...

@tool(name="search")
class SearchTool(ToolHandler):
    """Registered under an explicit name."""
    async def execute(self, arguments: dict) -> str: ...
```

To merge globally registered tools into an `AgentRuntime`, pass `use_global_registry=True`:

```python
runtime = AgentRuntime(
    model=model,
    tools=registry,          # explicit tools take precedence on name conflicts
    use_global_registry=True,  # @tool-decorated classes are merged in
    config=LoopConfig(),
)
```

Merge rules:
- When `use_global_registry=True`, the global registry is merged with `tools` at construction time.
- If the same name appears in both, the explicitly passed `tools` entry wins — it takes precedence.
- The global registry is never mutated; merge produces a new combined `ToolRegistry`.

This is an opt-in feature. `use_global_registry` defaults to `False`; existing callers that do not set it see no behaviour change.

## Terminate hint (P6)

A `ToolMessage` with `terminate=True` signals the loop to exit cleanly after the current iteration completes. No exception is raised; the loop drains normally.

```python
@dataclass
class ToolMessage:
    content: str
    is_error: bool = False
    terminate: bool = False   # when True, loop exits after this iteration; no exception raised
```

Usage — a tool that decides the task is complete can signal early exit without raising:

```python
class DoneCheckTool(ToolHandler):
    async def execute(self, arguments: dict) -> ToolMessage:
        if self._is_complete(arguments):
            return ToolMessage(content="Task complete.", terminate=True)
        return ToolMessage(content="Still working.")
```

The loop checks `ToolMessage.terminate` at the top of each iteration. If `True`, the loop exits after appending the tool result to the history and returns the full message list. This is distinct from `UserFixableError` (which bubbles up as an exception) and from `max_iterations` exhaustion (which also exits cleanly but is a limit, not a signal).

## Parallel tool execution (H7)

When the model emits a batch of tool calls in a single turn, the loop may dispatch them concurrently — but only when it is safe to do so. The decision is made by `can_parallelize()`, defined in `pyarnes_swarm.agent.parallel`.

```python
from pyarnes_swarm.agent.parallel import can_parallelize, SERIAL_TOOLS

def can_parallelize(calls: list[ToolCall]) -> bool:
    """Return True iff every call in `calls` is safe to dispatch concurrently.

    Conservative by design: any uncertainty resolves to False (serial dispatch).
    """
    ...
```

`can_parallelize` returns `False` if **any** of the following hold:

- Two calls share a path argument — for example, both write to `out.txt`. Detected by intersecting path-shaped argument values across the batch (any field whose value resembles a filesystem path).
- Any tool name in the batch is listed in `SERIAL_TOOLS`. This set captures handlers that mutate file-system state, hold module-global state, or otherwise must not run concurrently with anything (including themselves).

When `can_parallelize(calls)` is `False`, the loop falls back to sequential dispatch — the existing serial path is unchanged. When `True`, the loop awaits the calls together (`asyncio.gather`) and appends results in original order.

`SERIAL_TOOLS` is a module-level frozenset adopters can extend by composition — define a wrapper module that re-exports `can_parallelize` against an extended set if a custom tool needs to opt out of parallel dispatch. The default set covers the file-system mutating tools shipped with `pyarnes_swarm`.

This is conservative on purpose: parallel dispatch is a performance optimisation, not a correctness primitive. The cost of incorrectly parallelising two writes to the same path is data corruption; the cost of unnecessarily serialising two safe reads is latency. The defaults bias toward correctness.

## Stable public API surface

### `__all__` philosophy

`pyarnes_swarm.__init__` exports an explicit set of symbols via `__all__`. This is the contract adopters may depend on: anything in this table is protected by semver. `from pyarnes_swarm import *` yields only these names — nothing more leaks. Symbols importable only by deep path (e.g. `pyarnes_swarm.budget.Budget`) are implementation surfaces, not subject to the strongest stability guarantee.

### Symbol inventory

| Symbol | Notes |
|---|---|
| `pyarnes_swarm.Lifecycle` | Lifecycle tracking; exposes `.budget`, `.dump(path)`, `.load(path)` for session hooks |
| `pyarnes_swarm.Phase` | Lifecycle phase enum |
| `pyarnes_swarm.Budget` | Immutable token-spend cap; distinct from IterationBudget (mutable shared counter) |
| `pyarnes_swarm.IterationBudget` | Mutable shared iteration counter; held by `LoopConfig.budget` |
| `pyarnes_swarm.MessageCompactorConfig` | Compaction config; held by `LoopConfig.compaction_config` |
| `pyarnes_swarm.LoopBudget` | CC session budget (max_tokens/max_wall_seconds/max_calls); held by `Lifecycle.budget`; see `12-token-budget.md` |
| `pyarnes_swarm.TransientError` | Retry with exponential backoff |
| `pyarnes_swarm.LLMRecoverableError` | Returned as `ToolMessage` so the model adjusts |
| `pyarnes_swarm.UserFixableError` | Bubbles up for human input |
| `pyarnes_swarm.UnexpectedError` | Bubbles up for debugging |
| `pyarnes_swarm.HarnessError` | Base class for all harness errors |
| `pyarnes_swarm.Severity` | Severity levels for errors and violations |
| `pyarnes_swarm.ToolHandler` | Protocol — implement to define a tool |
| `pyarnes_swarm.ModelClient` | Concrete LiteLLM-backed model adapter |
| `pyarnes_swarm.ModelClientPort` | Protocol — implement to plug in a custom LLM backend |
| `pyarnes_swarm.get_logger` | Return the configured loguru logger |
| `pyarnes_swarm.configure_logging` | Configure log level and format at process start |
| `pyarnes_swarm.LogFormat` | Enum for log format (json / human) |
| `pyarnes_swarm.AgentRuntime` | Single-agent loop runner; use directly for single-agent setups or testing |
| `pyarnes_swarm.LoopConfig` | Loop retry and iteration configuration |
| `pyarnes_swarm.ToolMessage` | Structured tool result returned to the model |
| `pyarnes_swarm.ToolRegistry` | Registry mapping tool names to `ToolHandler` instances |
| `pyarnes_swarm.ToolCallLogger` | Writes JSONL tool-call records; stable field set, not stable field order |
| `pyarnes_swarm.ToolCallEntry` | Dataclass representing one logged tool call |
| `pyarnes_swarm.OutputCapture` | Context manager for capturing tool stdout/stderr |
| `pyarnes_swarm.CapturedOutput` | Result of an `OutputCapture` session |
| `pyarnes_swarm.read_cc_session` | Parse a Claude Code session transcript |
| `pyarnes_swarm.resolve_cc_session_path` | Resolve the path to the active Claude Code session file |
| `pyarnes_swarm.Guardrail` | Abstract base for all guardrails |
| `pyarnes_swarm.GuardrailChain` | Compose multiple guardrails in sequence |
| `pyarnes_swarm.PathGuardrail` | Block tool calls outside allowed filesystem roots |
| `pyarnes_swarm.CommandGuardrail` | Block disallowed shell commands |
| `pyarnes_swarm.ToolAllowlistGuardrail` | Permit only listed tool names |
| `pyarnes_swarm.SecretLeakGuardrail` | Detect and block secret leakage in tool arguments |
| `pyarnes_swarm.NetworkEgressGuardrail` | Restrict outbound network calls |
| `pyarnes_swarm.RateLimitGuardrail` | Enforce per-tool call rate limits |
| `pyarnes_swarm.Violation` | Sidecar record written when a guardrail fires |
| `pyarnes_swarm.append_violation` | Append a `Violation` to the violation log |
| `pyarnes_swarm.default_violation_log_path` | Return the default path for the violation log |
| `pyarnes_swarm.EvalSuite` | Define and run an evaluation suite |
| `pyarnes_swarm.EvalResult` | Result of a single evaluation run |
| `pyarnes_swarm.Scorer` | Abstract base for all scorers |
| `pyarnes_swarm.ExactMatchScorer` | Score by exact string match |
| `pyarnes_swarm.ToolUseCorrectnessScorer` | Score by whether the correct tools were called |
| `pyarnes_swarm.TrajectoryLengthScorer` | Score by trajectory length relative to a reference |
| `pyarnes_swarm.GuardrailComplianceScorer` | Score by guardrail violation rate |
| `pyarnes_swarm.Swarm` | Multi-agent orchestrator |
| `pyarnes_swarm.AgentSpec` | Declarative description of one agent |
| `pyarnes_swarm.TaskMeta` | Task context used by a `ModelRouter` to select a model |
| `pyarnes_swarm.ModelRouter` | Protocol — implement to plug in a custom routing strategy |
| `pyarnes_swarm.RuleBasedRouter` | Route by static model-tier rules |
| `pyarnes_swarm.LLMCostRouter` | Route by estimated token cost and context-window fit |
| `pyarnes_swarm.ModelTier` | Enum for model cost/capability tiers |
| `pyarnes_swarm.MessageBus` | Protocol — implement to plug in a custom message bus |
| `pyarnes_swarm.InMemoryBus` | In-process message bus for single-machine swarms |
| `pyarnes_swarm.TursoMessageBus` | Turso-backed durable message bus |
| `pyarnes_swarm.SecretStore` | Protocol — implement to supply secrets to agents |

### Explicitly private

These surfaces are intentionally excluded from the stability guarantee. Contributors may refactor them freely; adopters must not depend on them:

- `AgentRuntime._call_tool`, `AgentRuntime._dispatch`, and any `_`-prefixed helper on any public class.
- Log event string names (`"tool.pre"`, `"guardrail.command_blocked"`, etc.) — internal telemetry; adopters must not regex them.
- `ToolCallLogger` JSONL field order — the set of fields is stable, the order is not.
- `Lifecycle.history` concrete list type — the iterable contract is stable; mutations on the backing container are not.

### Semver policy

`CHANGELOG.md` at the repo root uses Keep-a-Changelog format seeded from `0.0.0 — initial stable surface declared`. The three tiers: **MAJOR** for removing or renaming any symbol from the table above, changing a `ToolHandler`/`Guardrail`/`Scorer`/`ModelRouter` base-class signature, or changing error-class inheritance; **MINOR** for new public symbols, new optional kwargs, new `Phase` values, new built-in `Guardrail` or `Scorer` subclasses; **PATCH** for bug fixes, docstring changes, and private-surface refactors.

## Tool Handler Sizing Constraint

A critical design constraint for all `ToolHandler.execute()` implementations is that they **must be ≤ 30 lines of code**. The handler's only responsibilities are parameter parsing, validation, and delegating to standard library or external libraries (e.g., executing standard CLI patterns like ingest/redact/sweep).

If a tool handler logic requires more than 30 lines, the core logic should be abstracted away and unit-tested in isolation. We recommend enforcing this using a code-length linting rule (e.g., `mccabe` or custom Flake8 limits) in `pyproject.toml`.
