# pyarnes_swarm — ModelRouter

## Why a ModelRouter?

Running every agent task on the most capable (most expensive) model wastes money on trivial subtasks. A ModelRouter inspects task signals — complexity, tool count, tool types — and assigns the cheapest model that can handle the task without sacrificing quality.

The efficiency feedback loop closes this cycle: `EvalSuite.run()` reports quality + cost per model, and `LLMCostRouter.observe()` updates routing weights so cheap models that perform well get promoted.

## Protocol (`ports.py`)

```python
class ModelRouter(Protocol):
    def route(self, spec: AgentSpec, meta: TaskMeta) -> str: ...
```

Returns a model ID string (e.g. `"claude-haiku-4-5-20251001"`, `"openrouter/mistralai/mistral-7b"`).

## Task signals (`TaskMeta`)

`TaskMeta` is **defined in `swarm.py`** alongside `Swarm` and `AgentSpec`. `routing.py` imports it from there. Do not re-define it.

```python
@dataclass(frozen=True)
class TaskMeta:
    """Signals used by ModelRouter to pick a model. Defined in swarm.py."""
    estimated_duration_seconds: float = 0.0
    tool_count: int = 0
    has_destructive_tools: bool = False   # rm, chmod, DROP TABLE, etc.
    complexity_score: float = 0.5         # 0.0 = trivial, 1.0 = complex
    model_hint: str | None = None         # from AgentSpec; router may honour or override
```

`complexity_score` is a 0–1 float. Callers compute it from task description length, tool schema complexity, or domain-specific signals. The router is agnostic to how it was computed.

## `RuleBasedRouter` — static rules

Ordered rules; first match wins. Last rule = catch-all.

```python
@dataclass(frozen=True)
class RoutingRule:
    model: str                    # model ID when this rule matches
    max_complexity: float = 1.0
    max_tools: int = 999
    allow_destructive: bool = True

class RuleBasedRouter:
    def __init__(self, rules: list[RoutingRule]) -> None: ...
    def route(self, spec: AgentSpec, meta: TaskMeta) -> str: ...
```

Example configuration:
```python
router = RuleBasedRouter([
    RoutingRule(max_tools=2, max_complexity=0.3,
                model="claude-haiku-4-5-20251001"),
    RoutingRule(max_tools=6, max_complexity=0.7,
                allow_destructive=False, model="claude-sonnet-4-6"),
    RoutingRule(model="claude-opus-4-7"),  # catch-all
])
```

## `LLMCostRouter` — cost-aware via LiteLLM

Uses `litellm.model_cost` to estimate cost **before dispatching**. Routing applies two sequential filters:

1. **Context window filter** — exclude any model whose `max_tokens` (from `litellm.model_cost`) is less than the task's `required_context_tokens`. A model that cannot fit the context is never selected, regardless of price.
2. **Complexity filter** — from the remaining candidates, select the tier whose `max_complexity >= task.complexity_score`.
3. **Cost sort** — within the matching tier, pick the cheapest model by `litellm.model_cost[model]["input_cost_per_token"]`.

If no model passes both filters, `LLMCostRouter.route()` raises `UserFixableError` — the caller must either compact the context or configure a model with a larger window.

```python
@dataclass(frozen=True)
class ModelTier:
    models: list[str]         # model IDs in this tier (any provider prefix)
    max_complexity: float     # tasks with score ≤ this value can use this tier

class LLMCostRouter:
    """Routes to cheapest model that meets complexity AND context window constraints.

    Selection order:
      1. Filter: model.max_tokens >= meta.required_context_tokens
      2. Filter: tier.max_complexity >= meta.complexity_score
      3. Sort:   cheapest by litellm.model_cost input_cost_per_token

    Raises UserFixableError if no model survives both filters.
    Default currency: EUR.
    """
    def __init__(self, tiers: list[ModelTier], currency: str = "EUR") -> None: ...
    def route(self, spec: AgentSpec, meta: TaskMeta) -> str: ...
    def estimated_cost_per_1k(self, model_id: str) -> Decimal: ...
    def observe(self, model_id: str, task_type: str, efficiency: float) -> None: ...
```

`TaskMeta` gains `required_context_tokens: int = 0` — set by the caller to the estimated context size for this task (overhead + history + output reserve). The router uses `litellm.get_max_tokens(model)` to check viability:

```python
# Inside LLMCostRouter.route():
from litellm import model_cost as _mc

viable = [
    m for m in tier.models
    if _mc.get(m, {}).get("max_tokens", 0) >= meta.required_context_tokens
]
```

Example configuration:
```python
router = LLMCostRouter(tiers=[
    ModelTier(models=["claude-haiku-4-5-20251001",
                      "openrouter/mistralai/mistral-7b"],
              max_complexity=0.35),
    ModelTier(models=["claude-sonnet-4-6",
                      "openrouter/anthropic/claude-3-5-sonnet"],
              max_complexity=0.75),
    ModelTier(models=["claude-opus-4-7"],
              max_complexity=1.0),
])
```

Within a tier, `LLMCostRouter` picks the cheapest model (by `litellm.model_cost` pricing). Cross-provider: the same model may be cheaper via OpenRouter than direct — the router compares them automatically.

**Auxiliary tasks** (compaction summariser, TALE self-estimation) are always routed to the cheapest-tier model regardless of `complexity_score`. They must not drive up session cost. See spec 12 for the full model selection table.

## Efficiency feedback loop

After an eval suite run, call `router.observe()` to feed cost-efficiency data back:

```python
# After EvalSuite.run():
efficiency = suite.cost_efficiency  # average_score / total_cost * 100
router.observe(
    model_id="claude-haiku-4-5-20251001",
    task_type="summarise",
    efficiency=efficiency,
)
```

`LLMCostRouter.observe()` adjusts internal weighting. Models that consistently score well on a task type at low cost get promoted (complexity ceiling raised). Models that underperform get demoted. This is a lightweight Bayesian update — no gradient descent, no external service.

`RuleBasedRouter` does not implement `observe()` (its rules are static by design). Use `LLMCostRouter` when you want the router to learn.

## `ModelClient` (`agent.py`)

Satisfies `ModelClientPort` Protocol using LiteLLM's unified API. Works with text, image, audio, and embedding models across any provider LiteLLM supports — no per-provider code required.

```python
class ModelClient:
    """Default model adapter — LiteLLM-backed, provider-agnostic.

    Accepts any model ID supported by LiteLLM, including provider-prefixed IDs:
        ModelClient("claude-haiku-4-5-20251001")
        ModelClient("openrouter/anthropic/claude-3-haiku")
        ModelClient("huggingface/mistralai/Mistral-7B-Instruct-v0.2")
        ModelClient("nvidia_nim/meta/llama3-70b-instruct")
        ModelClient("openai/gpt-4o")               # text + image
        ModelClient("openai/whisper-1")             # audio
        ModelClient("openai/text-embedding-3-small") # embeddings
    """
    def __init__(
        self,
        model: str,
        provider: ProviderConfig | None = None,
        secret_store: SecretStore | None = None,
        **litellm_kwargs: Any,
    ) -> None: ...

    async def next_action(self, messages: list[dict[str, Any]]) -> dict[str, Any]: ...
```

`TokenUsage` is extracted from `litellm_response.usage` and emitted to `BurnTracker` automatically when one is configured.

## Routing in the Swarm

`Swarm` uses the router to pick models per-spec:

```python
swarm = Swarm(
    router=LLMCostRouter(tiers=[...]),
    bus=TursoMessageBus(),
    agents=[
        AgentSpec(name="summariser", complexity_hint=0.2),
        AgentSpec(name="analyst",    complexity_hint=0.8),
    ],
)
```

The `summariser` gets a cheap model (complexity 0.2 → tier 1); the `analyst` gets a more capable model (complexity 0.8 → tier 2 or 3). The routing decision is logged as a structured event for auditability.
