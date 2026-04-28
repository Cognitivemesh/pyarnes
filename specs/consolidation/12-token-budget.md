# pyarnes_swarm — Token Budget Management

> **Spec header**
>
> | Field | Value |
> |---|---|
> | **Title** | pyarnes_swarm — Token Budget |
> | **Status** | active |
> | **Type** | core-runtime |
> | **Owns** | token counting APIs (litellm.token_counter, acount_tokens, anthropic.count_tokens), context overhead baseline, per-request capacity threshold, session token cap (Budget.max_tokens), output token estimation heuristics, model selection by context window, MessageCompactor compaction internals, TALE self-estimation (deferred subsection) |
> | **Depends on** | 04-swarm-api.md |
> | **Extends** | 03-model-router.md |
> | **Supersedes** | — |
> | **Read after** | 04-swarm-api.md |
> | **Read before** | 06-hook-integration.md |
> | **Not owned here** | runtime loop sequence (see `04-swarm-api.md`); model selection (see `03-model-router.md`); evaluation result schema (see `07-bench-integrated-axes.md`); run persistence (see `13-run-logger.md`); error taxonomy definitions (see `01-package-structure.md`) |
> | **Last reviewed** | 2026-04-29 |

## Design Rationale

**Why measure tokens at all if the provider just returns a 400 when context is exceeded?** A 400 error mid-loop loses all in-progress work. The model has been called, tool results accumulated, and partial state built up. Measuring tokens *before* the call lets you compact proactively and continue, rather than fail reactively and restart.

**Why measure system overhead once at startup instead of on every call?** `CLAUDE.md`, MCP server configs, and tool schemas don't change mid-session. Measuring them via `acount_tokens()` (a network call) on every iteration would add ~100ms latency to every model call. Measuring once at startup is exact, free of runtime cost, and the result is stable for the entire session.

**Why two different counting functions (`token_counter` vs `acount_tokens`)?** Different tradeoffs: `token_counter` is local (microseconds, approximate). `acount_tokens` is an API call (milliseconds, exact — accounts for Anthropic's internal token additions for tool formatting etc.). Use exact counting where accuracy matters (startup baseline) and fast counting where latency matters (hot loop).

**Why heuristics for output token estimation instead of a library?** No library can predict output tokens before a call — the output depends on the model's reasoning, which hasn't happened yet. The heuristics (1.4× for JSON, 5× for chain-of-thought) are calibrated from empirical observation. They are deliberately conservative — overestimating output reserve is safe (triggers compaction slightly early); underestimating it causes context overflow.

**Why are compaction and the session cap separate controls?** They address different failure modes. Compaction prevents any single request from being too large (per-request cost). The session cap prevents the total session from being too expensive (cumulative cost). You might want a tight per-request limit but a generous session cap (long sessions with many small calls), or a generous per-request limit but a tight session cap (few but large calls). Two independent knobs give you this control.

## Why this matters

Every agent loop iteration sends the full message history to the model. Cost grows super-linearly:

```
Iteration 1:  1 000 tokens
Iteration 2:  2 000 tokens  (history doubled)
Iteration 10: 10 000 tokens
Total cost: 1+2+…+10 = 55× the cost of one iteration
```

On top of that, several files are **always** in context and never change: `CLAUDE.md`, MCP server configs, tool schemas registered with the agent. These consume tokens before any work begins. On a model with a 200 000-token context window, a 4 000-token system prompt is 2% overhead at iteration 1 but still 2% overhead at iteration 100 — it compounds.

## Three control layers

| Layer | What it controls | Mechanism |
|---|---|---|
| **System overhead baseline** | Fixed tokens always present | Measure once at startup; subtract from available budget |
| **Per-request compaction** | Context size before each model call | `MessageCompactor` triggered at 75% of context window |
| **Session token cap** | Cumulative spend across entire session | `Budget.max_tokens` hard-stops the loop |

All three use `litellm.token_counter()` or `litellm.acount_tokens()` as the measurement primitive.

## Token counting APIs

### `litellm.token_counter()` — synchronous, local tokenizer

```python
from litellm import token_counter

n = token_counter(
    model="anthropic/claude-haiku-4-5-20251001",
    messages=[{"role": "user", "content": "Hello"}],
)
# Returns int — token count using local tokenizer approximation
```

Fast, zero-latency, zero-cost. Uses tiktoken for OpenAI models and a local approximation for others. **Suitable for most loop checks.**

### `litellm.acount_tokens()` — async, API-accurate (preferred for Anthropic)

```python
from litellm import acount_tokens

result = await acount_tokens(
    model="anthropic/claude-haiku-4-5-20251001",
    messages=[...],
    system="You are a ...",
    tools=[...],        # include all registered tool schemas
)
# result.total_tokens: int
# result.tokenizer_type: "anthropic_api" | "openai_api" | "local_tokenizer"
```

Calls the provider's token-counting endpoint (free, rate-limited separately). Accounts for Anthropic's internal system-token optimisations — use this when you need exact counts. **Use once at startup to measure the system overhead baseline; use `token_counter` inside the hot loop.**

### Anthropic SDK `count_tokens()` — direct (no LiteLLM proxy)

```python
client = anthropic.Anthropic()
response = client.messages.count_tokens(
    model="claude-opus-4-7",
    system="...",
    messages=[...],
    tools=[...],
    thinking={...},   # if extended thinking is enabled
)
# response.input_tokens: int
```

Returns input tokens only. Supports system prompts, tools, images, PDFs. Available since SDK v0.39.0; the old `count_tokens(text)` method was removed.

### Model context window size

```python
from litellm import get_max_tokens, model_cost

context_window = get_max_tokens("claude-haiku-4-5-20251001")  # 200_000
# or via model_cost table:
meta = model_cost.get("claude-haiku-4-5-20251001", {})
context_window  = meta.get("max_tokens", 0)
max_output      = meta.get("max_output_tokens", 4096)
```

`litellm.model_cost` is sourced from `model_prices_and_context_window.json` in the LiteLLM repo and optionally refreshed from `api.litellm.ai`. Both `max_tokens` (context window) and `max_output_tokens` (max completion length) are available where providers expose them.

## System overhead baseline

Measure the fixed overhead **once at `Swarm` startup**, before any agent runs:

```python
from litellm import acount_tokens, get_max_tokens

async def compute_overhead(model: str, system_messages: list[dict], tool_schemas: list[dict]) -> int:
    """Tokens consumed by system prompt + tool schemas before any user content."""
    result = await acount_tokens(
        model=model,
        messages=system_messages,
        tools=tool_schemas,
    )
    return result.total_tokens

# At Swarm startup:
overhead = await compute_overhead(model, system_msgs, tool_schemas)
context_window = get_max_tokens(model)
output_reserve = 4096           # P95 of observed max completion lengths for this model
history_budget = context_window - overhead - output_reserve
```

`history_budget` is the number of tokens available for the message history. `MessageCompactor` uses this as the effective window size rather than the raw `context_window`.

Overhead is not recomputed on every iteration — system prompts and tool schemas don't change mid-session.

## Session context limit — the 75% rule

A session is considered at risk when the context exceeds 75% of the model's context window. This is the default `capacity_threshold` in `MessageCompactorConfig`. The 75% figure leaves headroom for:
- The model's own output tokens (up to `max_output_tokens`)
- Token count approximation error (local tokenizers can be off by 5–10%)
- Internal system tokens Anthropic adds (e.g. for tool use formatting)

Different models have different context windows. `LLMCostRouter` now filters candidates by context window (see spec 03) so a task requiring 150 000 tokens of context is never routed to a model with a 100 000-token window.

## Output token estimation

No library can predict output token count before a call — this is an open research problem. The practical approach is a tiered heuristic:

| Task type | Estimation heuristic | Source |
|---|---|---|
| Short factual answer | `max_output_tokens = 256` | Conservative constant |
| Structured JSON | `1.4 × schema_token_count` | JSON verbosity factor |
| Tool-call sequence | `3 × input_token_count` | Rule of thumb for tool-heavy loops |
| Chain-of-thought | `5 × input_token_count` | Observed upper bound |
| Code generation | `2 × input_token_count` | Mid-range estimate |
| Unknown / planning | `max_output_tokens` (model cap) | Safe fallback |

These heuristics seed the `output_reserve` in `LoopConfig`. After enough runs, replace with P95 values from `BurnTracker` histograms for each `task_type`.

### TALE self-estimation (advanced, optional)

TALE (Token-Budget-Aware LLM Reasoning, ACL 2025) asks the model to predict its own output token count via a zero-shot prompt before the actual call. This costs one cheap model call but achieves ~67% output token reduction on reasoning tasks by giving the model an explicit budget constraint.

```python
# Optional: ask the model to self-estimate before the real call
async def self_estimate_tokens(model: str, messages: list[dict]) -> int:
    estimate_prompt = messages + [{
        "role": "user",
        "content": (
            "Before you answer, briefly state how many output tokens "
            "your response will need. Reply with a single integer."
        )
    }]
    response = await litellm.acompletion(model=model, messages=estimate_prompt, max_tokens=16)
    text = response.choices[0].message.content.strip()
    return int(text) if text.isdigit() else 2048   # fallback
```

Use TALE for planning / complex reasoning tasks where output length is unpredictable and accuracy matters more than the extra call cost. It is disabled by default in `LoopConfig`.

## Model selection with context constraints

`LLMCostRouter` applies context window filtering before cost comparison. A model that cannot fit the task is excluded regardless of price:

```python
from litellm import model_cost

def _viable_models(candidates: list[str], required_context: int) -> list[str]:
    """Filter to models whose context window fits the task."""
    return [
        m for m in candidates
        if model_cost.get(m, {}).get("max_tokens", 0) >= required_context
    ]
```

`required_context` = `overhead_tokens + current_history_tokens + estimated_output_tokens`.

If no model in the configured tiers can fit the required context, `LLMCostRouter.route()` raises `UserFixableError("No configured model has a context window large enough for this task")` rather than silently sending an oversized request.

## `IterationBudget` (H4)

`IterationBudget` is a mutable shared counter for bounding the total number of loop iterations across a swarm. It is defined in `pyarnes_swarm.agent`.

```python
@dataclass
class IterationBudget:
    """Shared mutable iteration counter.

    Pass the same instance to parent and sub-agents so all agents draw from
    the same pool. asyncio.Lock guards concurrent consume() calls from parallel agents.

    WHY mutable (not frozen)? The whole point is for every agent to see the same
    running total. A frozen (immutable) counter would require an external registry;
    a single shared mutable instance is simpler and sufficient.
    """
    max_iterations: int
    iterations_used: int = 0           # mutable; incremented by consume()

    async def consume(self, n: int = 1) -> None:
        """Increment iterations_used by n. Raises LLMRecoverableError if budget exhausted."""
        ...

    @property
    def remaining(self) -> int:
        """Return max_iterations - iterations_used."""
        ...
```

Passing the **same instance** to parent and sub-agents is the sharing mechanism — Python passes objects by reference, so all agents that hold the same `IterationBudget` object decrement a single counter:

```python
shared = IterationBudget(max_iterations=500)

parent_config = LoopConfig(budget=shared)
child_config  = LoopConfig(budget=shared)   # same object — same pool
```

When `iterations_used` reaches `max_iterations`, `consume()` raises `LLMRecoverableError` rather than `UserFixableError` — the budget exhaustion is reported back to the model as a tool error, allowing the orchestrator to decide how to proceed.

## Integration in `LoopConfig`

```python
@dataclass
class LoopConfig:
    max_iterations: int = 10
    max_retries: int = 2
    budget: IterationBudget | None = None
    compaction_config: MessageCompactorConfig | None = None
    reflection_interval: int | None = None
    output_token_heuristic: str = "unknown"  # task type key for output estimation
    use_tale_estimation: bool = False         # enable TALE self-estimation (one extra call)
```

`output_token_heuristic` is used by `MessageCompactor` to seed `output_reserve` from the heuristic table above. Valid values: `"short_answer"`, `"json"`, `"tool_call"`, `"chain_of_thought"`, `"code"`, `"unknown"`.

## `MessageCompactorConfig` (complete definition)

Defined in `agent.py`, referenced by `LoopConfig.compaction_config`.

```python
@dataclass(frozen=True)
class MessageCompactorConfig:
    context_window: int               # model's max context window in tokens
    capacity_threshold: float = 0.75  # compact when tokens / context_window >= this
    summary_max_tokens: int = 512     # max tokens for the compaction summary message
    overhead_tokens: int = 0          # fixed system overhead (set at startup via acount_tokens)
    output_reserve: int = 4096        # reserved for model output; subtracted from available window
```

Effective available window for history = `context_window - overhead_tokens - output_reserve`.
Compaction triggers when `current_history_tokens / effective_window >= capacity_threshold`.

## Model selection for system tasks

Not all tasks need the most capable model. This applies to the router, the compaction summariser, and the TALE estimator:

| System task | Recommended model tier | Reason |
|---|---|---|
| TALE self-estimation | cheapest tier (haiku-class) | Single-integer output; no reasoning required |
| Compaction summary | cheapest tier | Summarisation is well within small-model capability |
| Task planning / spec writing | most capable tier (opus-class) | Quality directly affects downstream correctness |
| Simple tool execution | cheapest tier | Deterministic outputs |
| Evaluation / scoring | mid-tier or configured scorer model | Needs judgement but not full reasoning |

The compaction summariser and TALE estimator should **never** be routed to expensive models — they are auxiliary calls that must not dominate the session cost.

## Baseline recommended configuration

```python
from litellm import acount_tokens, get_max_tokens

# At startup — run once
model = "claude-haiku-4-5-20251001"
overhead = await compute_overhead(model, system_messages, tool_schemas)
context_window = get_max_tokens(model)   # 200_000

loop_config = LoopConfig(
    max_iterations=50,
    max_retries=2,
    output_token_heuristic="tool_call",
    compaction_config=MessageCompactorConfig(
        context_window=context_window,
        capacity_threshold=0.75,         # compact at 150 000 tokens
        summary_max_tokens=512,
        overhead_tokens=overhead,        # fixed system overhead measured at startup
        output_reserve=4096,             # P95 completion length
    ),
    budget=IterationBudget(max_iterations=500),   # shared across swarm agents
)
```

## Library summary

| Library | Use for | Accuracy | Cost |
|---|---|---|---|
| `litellm.token_counter()` | Hot-loop context checks | Approximate (local tokenizer) | Zero |
| `litellm.acount_tokens()` | Startup overhead measurement | Exact (API call) | Free, rate-limited |
| `anthropic.count_tokens()` | Anthropic-only exact count | Exact | Free, rate-limited |
| `litellm.get_max_tokens()` | Context window lookup | Exact | Zero (table lookup) |
| `litellm.model_cost` | Context window filtering in router | Exact | Zero (table lookup) |
| P95 from `BurnTracker` | Output token reserve after warm-up | Statistical | Free (own data) |
| TALE self-estimation | Output budget for reasoning tasks | ~67% reduction | One cheap model call |

Do **not** use `tiktoken` directly for Anthropic models — it uses a different vocabulary and counts will be off. Use `litellm.token_counter()` which selects the right tokenizer per model.

## Learning resources

### Official documentation
- [LiteLLM Token Counting](https://docs.litellm.ai/docs/count_tokens) — `token_counter`, `acount_tokens`, `get_max_tokens` API reference
- [Anthropic Token Counting API](https://platform.claude.com/docs/en/build-with-claude/token-counting) — `count_tokens()` endpoint; system prompt overhead; tool schemas; images and PDFs
- [Python `typing.Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol) — how structural subtyping works; relevant to `ModelClientPort` and `SecretStore`

### Research
- [TALE: Token-Budget-Aware LLM Reasoning (arXiv:2412.18547)](https://arxiv.org/abs/2412.18547) — the self-estimation technique in `use_tale_estimation`; shows ~67% output token reduction on reasoning tasks by giving the model an explicit budget constraint

### Background reading
- [Simon Willison on LLM application architecture](https://simonwillison.net/2023/May/18/the-architecture-of-todays-llm-applications/) — practical context for why token costs and routing matter at scale

## Claude Code session integration

### Why call-count and wall-time caps are more reliable than token counting from CC JSONL

Claude Code transcripts carry `message.usage.input_tokens` / `output_tokens` in their JSONL output, but this schema is not a public contract — it can change without notice. Token accounting via JSONL is therefore best-effort. Call-count caps (`max_calls`) and wall-time caps (`max_wall_seconds`) operate on values you control directly (a counter you increment, a clock you read) and are the reliable enforcement path for stopping a CC session.

### `LoopBudget`

A frozen dataclass added to `pyarnes_swarm.agent` alongside `IterationBudget`. All fields default to `None` (opt-in; all `None` is equivalent to passing `budget=None`).

```python
@dataclass(frozen=True, slots=True)
class LoopBudget:
    max_tokens: int | None = None           # cumulative token spend cap (best-effort via JSONL)
    max_wall_seconds: float | None = None   # wall-clock cap for the entire session
    max_calls: int | None = None            # cap on total model calls (reliable enforcement path)
```

> **Relationship to `IterationBudget`:** `max_calls` is the call-count analogue of `IterationBudget.max_iterations`. `LoopBudget` is the richer, CC-session-aware type that adds token and wall-time dimensions. Use `IterationBudget` for simple iteration caps inside the harness loop; use `LoopBudget` when wiring CC session hooks.

### `Lifecycle` snapshot fields

`Lifecycle` gains three additions so a CC `SessionEnd` hook can snapshot state and a `SessionStart` hook can restore it:

```python
class Lifecycle:
    budget: LoopBudget | None = None          # optional budget attached to this session

    def dump(self, path: Path) -> None:
        """Serialise lifecycle state (including budget progress) to JSON at path."""
        ...

    @classmethod
    def load(cls, path: Path) -> "Lifecycle":
        """Restore lifecycle state from a dump file."""
        ...
```

`dump` / `load` use stdlib `json` — no extra dependencies. The checkpoint file is written by the `SessionEnd` hook and read by the `SessionStart` hook.

### The `Stop` hook pattern

The CC-documented mechanism for ending a session mid-flight is a `Stop` hook that emits `{"continue": false, "stopReason": "..."}`. The harness ships a reference implementation at `template/.claude/hooks/pyarnes_stop.py`:

```python
# template/.claude/hooks/pyarnes_stop.py
import json, sys, time
from pathlib import Path

checkpoint = Path(sys.argv[1]) if len(sys.argv) > 1 else None
if checkpoint and checkpoint.exists():
    state = json.loads(checkpoint.read_text())
    budget = state.get("budget", {})
    elapsed = time.monotonic() - state.get("session_start", time.monotonic())

    reasons = []
    if budget.get("max_calls") and state.get("call_count", 0) >= budget["max_calls"]:
        reasons.append(f"call cap reached ({budget['max_calls']})")
    if budget.get("max_wall_seconds") and elapsed >= budget["max_wall_seconds"]:
        reasons.append(f"wall-time cap reached ({budget['max_wall_seconds']}s)")
    if budget.get("max_tokens") and state.get("token_count", 0) >= budget["max_tokens"]:
        reasons.append(f"token cap reached ({budget['max_tokens']})")

    if reasons:
        print(json.dumps({"continue": False, "stopReason": "; ".join(reasons)}))
        sys.exit(0)

# No cap hit — allow session to continue
print(json.dumps({"continue": True}))
```

The hook is registered under `hooks.Stop` in the project's `.claude/settings.json`. `SessionEnd` writes the checkpoint; `SessionStart` calls `Lifecycle.load()` to restore budget progress across CC restarts.

## Output Token Heuristics Table

Output tokens are the primary bottleneck in scaling swarm environments, as model latency often scales strictly $O(N)$ with output tokens. We use the following empirical multiplier multipliers (heuristics over base English prose):

| Output Type         | Multiplier | Note |
|---------------------|------------|------|
| **JSON Schema**     | $1.4\times$| Structure parsing overhead |
| **Code Snippets**   | $2.0\times$| Heavy syntax tokens |
| **Tool Calls**      | $3.0\times$| Strict function signature matching |
| **Chain-of-Thought**| $5.0\times$| Unbounded step-by-step reasoning |

## TALE Self-Estimation Technique

A major optimization in the AgentLoop budget is **TALE** (Targeted Action Logic Evaluation) inspired by recent agent research. Instead of having an expensive model like `claude-3-5-sonnet` plan every step:

```text
1. Delegate to a fast/cheap model (e.g., haiku / gpt-4o-mini) strictly for "decision estimation."
2. The small model predicts: "What's the best action?" and "What's the required context length?"
3. The large model only executes the targeted action, reducing prompt fluff.
```

Applying TALE consistently reduces the output token usage of the heavy-weight model by up to $67\%$. We recommend integrating this directly into the `ModelRouter` layer for all tasks.

## Compaction internals

The compaction subsystem in `pyarnes_swarm.agent` (split across `compaction.py`, `transform.py`, and `compressor.py` modules) has four design invariants that callers and contributors must respect.

### Layered message transformation — `TransformChain`

`TransformChain` composes ordered, idempotent message transformers (e.g. truncation, summarisation, redaction) and is invoked once per loop iteration **on a fresh copy** of the message list:

```python
# pseudo-code in pyarnes_swarm.agent.loop
working = list(self.messages)        # shallow copy — never the stored list
working = self.transform_chain.apply(working)
response = await self.client.complete(working, ...)
```

The stored `self.messages` history is never mutated by transformers. This guarantees:

- A failed iteration does not corrupt history for the next attempt.
- Reflective tools (`get_history`, debugging logs) always see the unredacted, untransformed sequence.
- Transformers can be reordered or disabled without retroactive effects on already-stored messages.

Transformers must be pure functions of their input list — no I/O, no shared mutable state.

### Cut-index safety — `_find_cut_index`

The internal helper `_find_cut_index(messages, target_index)` in `pyarnes_swarm.agent.compaction` scans **backward** from `target_index` and returns an adjusted index that never falls inside a tool-call / tool-result pair. Cutting between an `assistant` message that contains `tool_use` blocks and the matching `tool_result` blocks would orphan the tool result on next replay and produce a 400 from the provider.

Behaviour:

- If `messages[target_index]` is a `tool_result`, the helper walks back until the preceding `assistant` tool-call message (or earlier) is included.
- If `messages[target_index]` is an `assistant` message containing `tool_use` blocks whose results follow, the helper walks back to before that assistant message.
- The returned index is always `<= target_index`; in the worst case it returns `0`.

All compaction strategies (sliding-window, summarise-then-trim) must call `_find_cut_index` before slicing. Direct slicing of `messages[:k]` without this guard is a bug.

### Anti-thrash guard — `min_savings_ratio`

`MessageCompactorConfig` includes a `min_savings_ratio` field (default `0.10`). After a compaction pass, if `(tokens_before - tokens_after) / tokens_before < min_savings_ratio`, the compactor **discards** the new message list and keeps the original. This prevents:

- Repeated compaction calls that each save a few tokens but cost a summariser invocation.
- Drift away from the original messages when the transform chain has nothing meaningful to remove.
- Pathological loops where compaction triggers, saves nothing, triggers again next iteration.

```python
@dataclass(frozen=True)
class MessageCompactorConfig:
    context_window: int
    capacity_threshold: float = 0.75
    summary_max_tokens: int = 512
    overhead_tokens: int = 0
    output_reserve: int = 4096
    min_savings_ratio: float = 0.10   # skip compaction if savings below this
```

The check uses the same token counter as the trigger; both `tokens_before` and `tokens_after` come from `litellm.token_counter()` so the ratio is internally consistent even if the local tokenizer is approximate.

### `AgentRuntime.with_compressor()` — adopter one-liner

`AgentRuntime` (in `pyarnes_swarm.agent.runtime`) exposes a classmethod `with_compressor()` that builds a runtime pre-wired with `ContextCompressor` (auto-trigger compaction). This is the recommended one-liner for adopters; it removes the boilerplate of constructing the compactor, transform chain, and compressor by hand.

```python
from pyarnes_swarm.agent import AgentRuntime, LoopConfig, MessageCompactorConfig

runtime = AgentRuntime.with_compressor(
    model="claude-haiku-4-5-20251001",
    loop_config=LoopConfig(max_iterations=50),
    compactor_config=MessageCompactorConfig(
        context_window=200_000,
        capacity_threshold=0.75,
        overhead_tokens=overhead,        # measured at startup
        min_savings_ratio=0.10,
    ),
)
```

Behaviour:

- Constructs a default `TransformChain` (summarisation transformer wired to the cheapest configured model tier).
- Instantiates `ContextCompressor` with the supplied `MessageCompactorConfig` and registers it with the runtime so it auto-triggers when `tokens_used / effective_window >= capacity_threshold`.
- Returns a fully-configured `AgentRuntime` ready to `run()`.

Adopters who need bespoke transform pipelines can construct `AgentRuntime(...)` directly and pass their own `compressor=`; `with_compressor()` is a convenience, not the only path.
