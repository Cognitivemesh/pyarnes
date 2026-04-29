# pyarnes_swarm — Provider Configuration

> **Spec header**
>
> | Field | Value |
> |---|---|
> | **Title** | pyarnes_swarm — Provider Config (Through Which Provider) |
> | **Status** | active |
> | **Type** | integrations-safety |
> | **Owns** | ProviderConfig, supported providers (OpenRouter, HuggingFace, NVIDIA NIM, Anthropic Direct), provider prefix resolution, ProviderConfig integration with ModelClient, adding a new provider |
> | **Depends on** | 03-model-router.md, 22-transport.md |
> | **Extends** | 11-secrets.md |
> | **Supersedes** | — |
> | **Read after** | 22-transport.md |
> | **Read before** | 11-secrets.md |
> | **Not owned here** | model selection (see `03-model-router.md`); transport adapters / schema conversion (see `22-transport.md`); secrets storage (see `11-secrets.md`); evaluation cost calculation (see `07-bench-integrated-axes.md`) |
> | **Last reviewed** | 2026-04-29 |

## Design Rationale

**Why `ProviderConfig` instead of hardcoding provider logic in `ModelClient`?** `ModelClient` uses LiteLLM's unified API — the provider prefix in the model ID (`openrouter/anthropic/claude-3-haiku`) already tells LiteLLM where to send the request. `ProviderConfig` adds only the secret resolution step: which key in the `SecretStore` holds the API key for this provider. Keeping these separate means adding a new provider requires zero code changes to `ModelClient` — only a new `ProviderConfig`.

**Why does `LLMCostRouter` compare costs across providers, not just across models?** The same model may be cheaper via OpenRouter than via Anthropic Direct (OpenRouter adds a small markup but may offer better rate limits or more models per key). The router queries `litellm.model_cost` for both the bare model ID and the `openrouter/` prefixed version and picks the cheaper one. Without cross-provider comparison, you'd need to manually benchmark prices and update configurations when they change.

**Why does `ModelClient` call `store.get()` (raises `KeyError`) rather than `store.get_optional()` (returns `None`)?** A missing API key should fail immediately and loudly at the first model call, not silently produce a `None` that gets passed to LiteLLM and comes back as an opaque `401 Unauthorized`. `KeyError` at `store.get()` tells you exactly what's missing.

## Supported providers

`ModelClient` routes calls to any model supported by LiteLLM's unified API. The caller specifies a provider-prefixed model ID; LiteLLM handles authentication and request shaping transparently.

| Provider | LiteLLM prefix | Example model ID |
|---|---|---|
| **Anthropic Direct** | `anthropic/` or bare | `claude-haiku-4-5-20251001` |
| **OpenRouter** | `openrouter/` | `openrouter/anthropic/claude-3-haiku` |
| **HuggingFace Inference** | `huggingface/` | `huggingface/mistralai/Mistral-7B-Instruct-v0.2` |
| **NVIDIA NIM** | `nvidia_nim/` | `nvidia_nim/meta/llama3-70b-instruct` |

OpenRouter and NVIDIA NIM give access to hundreds of models with a single API key. HuggingFace Inference provides serverless endpoints for open models.

## `ProviderConfig`

Binds a `ModelClient` to a specific provider's credentials and endpoint.

```python
@dataclass(frozen=True)
class ProviderConfig:
    """Provider binding for ModelClient.

    Attributes:
        provider_type: One of "anthropic", "openrouter", "huggingface", "nvidia_nim".
        api_key_name:  Key name in the SecretStore (e.g. "openrouter").
                       The SecretStore resolves this to the actual API key at runtime.
        base_url:      Override the provider endpoint. Required for NVIDIA NIM
                       self-hosted deployments. None = use LiteLLM default.
    """
    provider_type: str
    api_key_name: str
    base_url: str | None = None
```

## Example configurations

```python
from pyarnes_swarm.secrets import ProviderConfig

# Anthropic Direct
anthropic = ProviderConfig(
    provider_type="anthropic",
    api_key_name="anthropic",
)

# OpenRouter (access 200+ models via one key)
openrouter = ProviderConfig(
    provider_type="openrouter",
    api_key_name="openrouter",
)

# HuggingFace Inference (serverless)
huggingface = ProviderConfig(
    provider_type="huggingface",
    api_key_name="huggingface",
)

# NVIDIA NIM (cloud-hosted NIM endpoint)
nvidia_cloud = ProviderConfig(
    provider_type="nvidia_nim",
    api_key_name="nvidia_nim",
)

# NVIDIA NIM (self-hosted, custom endpoint)
nvidia_selfhosted = ProviderConfig(
    provider_type="nvidia_nim",
    api_key_name="nvidia_nim",
    base_url="http://localhost:8000/v1",
)
```

## Using `ProviderConfig` with `ModelClient`

```python
from pyarnes_swarm import ModelClient
from pyarnes_swarm.secrets import ProviderConfig, ChainedSecretStore, KeyringSecretStore, EnvSecretStore

store = ChainedSecretStore(
    KeyringSecretStore(namespace="pyarnes"),
    EnvSecretStore(prefix="PYARNES_"),
)

# OpenRouter: the same interface, any model
client = ModelClient(
    model="openrouter/anthropic/claude-3-haiku",
    provider=ProviderConfig(provider_type="openrouter", api_key_name="openrouter"),
    secret_store=store,
)
```

The `ModelClient` calls `store.get(provider.api_key_name)` at first use to resolve the API key. The key is never stored in the config object — it is fetched from the `SecretStore` at runtime.

## Cross-provider cost comparison via `LLMCostRouter`

`LLMCostRouter` compares pricing across all providers using `litellm.model_cost`:

```python
from pyarnes_swarm.routing import LLMCostRouter, ModelTier

router = LLMCostRouter(
    tiers=[
        # Tier 1: cheap, fast, max_complexity 0.35
        ModelTier(
            models=[
                "claude-haiku-4-5-20251001",              # Anthropic direct
                "openrouter/anthropic/claude-3-haiku",    # same model via OpenRouter
                "openrouter/mistralai/mistral-7b",        # cheaper open model
            ],
            max_complexity=0.35,
        ),
        # Tier 2: mid-range
        ModelTier(
            models=[
                "claude-sonnet-4-6",
                "openrouter/anthropic/claude-3-5-sonnet",
                "nvidia_nim/meta/llama3-70b-instruct",
            ],
            max_complexity=0.75,
        ),
        # Tier 3: most capable
        ModelTier(
            models=["claude-opus-4-7"],
            max_complexity=1.0,
        ),
    ],
    currency="EUR",
)
```

Within a tier, `LLMCostRouter` picks the model with the lowest `litellm.model_cost[model]["input_cost_per_token"]`. The same Anthropic model may be cheaper on OpenRouter after markup — the router discovers this automatically.

`estimated_cost_per_1k(model_id)` returns the current LiteLLM pricing in EUR for external inspection.

### Provider prefix lookup

`litellm.model_cost` keys vary by provider — the same underlying model has different keys depending on which provider serves it. Reference for the supported providers:

| Provider / Router | Model Prefix | Example Config Key | Look-up Pattern |
|---|---|---|---|
| **OpenRouter** | `openrouter/` | `openrouter/claude-3-5-sonnet` | `litellm.model_cost["openrouter/claude-3-5-sonnet"]` |
| **Anthropic** | `anthropic/` | `anthropic/claude-3-5-sonnet-20240620` | `litellm.model_cost["claude-3-5-sonnet-20241022"]` |
| **OpenAI** | `openai/` | `openai/gpt-4o` | `litellm.model_cost["gpt-4o"]` |

## CI configuration

For CI, store secrets as GitHub Actions environment secrets:

```yaml
# .github/workflows/ci.yml
env:
  PYARNES_ANTHROPIC: ${{ secrets.PYARNES_ANTHROPIC }}
  PYARNES_OPENROUTER: ${{ secrets.PYARNES_OPENROUTER }}
  PYARNES_HUGGINGFACE: ${{ secrets.PYARNES_HUGGINGFACE }}
  PYARNES_NVIDIA_NIM: ${{ secrets.PYARNES_NVIDIA_NIM }}
```

`ChainedSecretStore(KeyringSecretStore(...), EnvSecretStore(prefix="PYARNES_"))` falls back to env vars on CI runners where there is no keychain daemon.

## Adding a new provider

1. Identify the LiteLLM prefix for the new provider
2. Create a `ProviderConfig` with `provider_type` matching the prefix
3. Store the API key: `keyring.set_password("pyarnes", "<api_key_name>", "<key>")`
4. Pass the `ProviderConfig` to `ModelClient`

No code changes to `pyarnes_swarm` are required. LiteLLM handles the rest.

## Streaming transport

For streaming responses, implement `StreamingProviderTransport` (a sub-protocol of `ProviderTransport`; see `22-transport.md`). Non-streaming providers only need `ProviderTransport`.

## Open questions or deferred items

- **Rate-limit / 429 recovery.** No specified behaviour when a provider returns HTTP 429 or equivalent. Should the router fall back to a lower-cost tier, retry with backoff, or surface as `TransientError`? Different providers warrant different policies.
- **Provider-specific timeout tuning.** Provider latency profiles vary (Anthropic Direct vs HuggingFace Inference vs NIM). One global timeout is suboptimal; per-provider overrides are not yet specified.
- **Failover policy.** When a primary provider is unavailable, should the router transparently route to a secondary, surface as an error, or block until the primary recovers?

By indexing parameters uniformly in the routing abstractions, the framework guarantees reliable Token Budgeting measurements and threshold checks for diverse backends.
