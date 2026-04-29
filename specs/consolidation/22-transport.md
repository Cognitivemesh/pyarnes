# pyarnes_swarm — Transport Layer

> **Spec header**
>
> | Field | Value |
> |---|---|
> | **Title** | pyarnes_swarm — Transport (Through Which Transport) |
> | **Status** | active |
> | **Type** | integrations-safety |
> | **Owns** | ProviderTransport Protocol, LiteLLMTransport adapter, TransportModelClient, tool-schema conversion, raw vs LiteLLM transport selection |
> | **Depends on** | 03-model-router.md |
> | **Extends** | 04-swarm-api.md |
> | **Supersedes** | — |
> | **Read after** | 20-message-safety.md |
> | **Read before** | 10-provider-config.md |
> | **Not owned here** | model selection (see `03-model-router.md`); provider config (see `10-provider-config.md`); secrets (see `11-secrets.md`); inter-agent message bus (see `02-message-bus.md`) — bus is for cross-process messaging, transport is for model-call plumbing |
> | **Extended by** | 04-swarm-api.md, 10-provider-config.md |
> | **Last reviewed** | 2026-04-29 |

## Design Rationale

**Why does `TransportModelClient` adapt `ProviderTransport` → `ModelClient` instead of changing `AgentLoop` directly?** `AgentLoop` depends only on the `ModelClient` protocol. Introducing a new transport backend — LiteLLM, a stub, a future provider — requires zero changes to `AgentLoop`. Only the transport changes. This is the open/closed principle applied concretely: `AgentLoop` is closed to modification; the transport layer is open to extension.

**Why is the `litellm` import deferred inside `LiteLLMTransport.complete()` rather than at module level?** `litellm` is a heavy dependency (~50 MB of models and data files). Importing it at module load time penalises every process that imports `pyarnes_swarm.transport`, even processes that never call a model. Deferring the import to the first `complete()` call keeps cold start fast for tests, hooks, and utilities that use other parts of the library.

**Why is `ToolRegistry.register_schema()` optional?** Tools that register a JSON schema get automatic argument conversion across providers (OpenAI function-calling format ↔ Anthropic tool-use format). Tools that don't register are excluded from conversion and receive raw arguments. This is progressive enhancement: adopters opt in per-tool without any breaking change to existing tools.

**Why does `repair_json_args` raise `LLMRecoverableError` on unrepaired JSON rather than returning the broken dict?** A partial or malformed tool-call argument silently passed to a tool handler causes data corruption that is hard to trace. An `LLMRecoverableError` is returned to the model as a `ToolMessage`, prompting it to re-emit a clean call. One transparent retry is better than silent data corruption.

## Transport protocol (H2+P10)

`ProviderTransport` is a structural `Protocol` — any class that implements `complete()` satisfies it without inheriting from a base class.

```python
from typing import Protocol

class ProviderTransport(Protocol):
    """Structural protocol for provider backends.

    Implement this to add a new provider without touching AgentLoop.
    Module: pyarnes_swarm.transport
    """

    async def complete(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        **kwargs,
    ) -> dict:
        """Send a completion request; return the provider's raw response dict."""
        ...
```

`TransportModelClient` wraps any `ProviderTransport` and exposes the `ModelClient` protocol that `AgentLoop` expects:

```python
from pyarnes_swarm.transport import TransportModelClient, LiteLLMTransport

transport = LiteLLMTransport()   # litellm import deferred until first complete()
client = TransportModelClient(transport=transport, model="openrouter/anthropic/claude-3-haiku")
```

`AgentLoop` receives a `ModelClient` — it does not know whether the underlying transport is LiteLLM, a stub, or a future provider.

Module: `pyarnes_swarm.transport`

## Tool schema conversion (P10)

`ToolRegistry.register_schema()` links a tool name to its JSON schema. When a transport that requires provider-specific argument formatting (e.g. OpenAI function-calling) calls `complete()`, `TransportModelClient` converts only the registered tools:

```python
from pyarnes_swarm.transport import ToolRegistry

registry = ToolRegistry()
registry.register_schema("search", {
    "type": "object",
    "properties": {
        "query": {"type": "string"},
    },
    "required": ["query"],
})
```

Tools without a registered schema are passed through as-is. This means adopters can introduce schema-based conversion tool-by-tool without breaking existing tool handlers.

Module: `pyarnes_swarm.transport`

## JSON repair (H3)

`repair_json_args` attempts to fix malformed JSON that the model emits as tool-call arguments — truncated strings, trailing commas, unquoted keys — using a best-effort repair pass.

```python
from pyarnes_swarm.transport.repair import repair_json_args

args = repair_json_args('{"query": "hello world"')   # missing closing brace
# Returns: {"query": "hello world"}
```

If the repair pass cannot produce a valid dict, `repair_json_args` raises `LLMRecoverableError`. The error is surfaced as a `ToolMessage` so the model re-emits a clean call on the next iteration.

`LiteLLMTransport.complete()` calls `repair_json_args` on each tool-call argument block before dispatching to the handler. The repair is transparent to `AgentLoop`.

Module: `pyarnes_swarm.transport.repair`

## Streaming transport (P8)

`StreamingProviderTransport` is an optional sub-protocol that extends `ProviderTransport` with a `stream_complete()` method:

```python
from typing import AsyncIterator, Protocol

class StreamingProviderTransport(ProviderTransport, Protocol):
    """Optional sub-protocol for transports that support streaming.

    Non-streaming transports only need to implement ProviderTransport.
    Module: pyarnes_swarm.transport
    """

    async def stream_complete(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        **kwargs,
    ) -> AsyncIterator[dict]:
        """Yield partial response chunks as they arrive from the provider."""
        ...
```

`LiteLLMTransport` implements `StreamingProviderTransport`. Transports that do not implement `stream_complete()` satisfy only `ProviderTransport` and are unaffected by streaming. `TransportModelClient` checks at runtime whether the underlying transport supports streaming and falls back to `complete()` for non-streaming transports.

Module: `pyarnes_swarm.transport`
