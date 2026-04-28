# pyarnes_swarm — Token Budget Management

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
