# pyarnes_swarm — Loop Hooks

> **Spec header**
>
> | Field | Value |
> |---|---|
> | **Title** | pyarnes_swarm — Internal Loop Hooks |
> | **Status** | active |
> | **Type** | integrations-safety |
> | **Owns** | internal in-process Python hooks (PreToolHook, PostToolHook), async hook protocols, steering queue injection, hook insertion points in AgentLoop |
> | **Depends on** | 04-swarm-api.md |
> | **Extends** | — |
> | **Supersedes** | — |
> | **Read after** | 12-token-budget.md |
> | **Read before** | 06-hook-integration.md |
> | **Not owned here** | external Claude Code hooks — stdin JSON, exit codes, settings.json registration (see `06-hook-integration.md`); model routing (see `03-model-router.md`); evaluation (see `07-bench-integrated-axes.md`); error taxonomy definitions (see `01-package-structure.md`) |
> | **Last reviewed** | 2026-04-29 |

## Design Rationale

**Why `PreToolHook`/`PostToolHook` instead of just `GuardrailChain`?** Guardrails veto tool calls based on policy — they answer a yes/no question ("is this call allowed?"). Hooks modify args or results based on logic — they answer a transformation question ("what should this call actually receive/return?"). The two are complementary: a `PreToolHook` might rewrite a relative path to absolute before dispatch; a guardrail would block a path that escapes the allowed root. Having separate extension points keeps policy enforcement and data transformation from conflating into one tangled callable.

**Why does `PreToolHook` return modified args or `None` rather than a bool veto?** `None` means pass-through (unchanged args), keeping the common case zero-cost: a hook that only needs to intercept specific tools can return `None` for everything else with no allocation. The veto mechanism is `raise LLMRecoverableError` — consistent with how `InjectionGuardrail` vetoes in Phase 1. Using the error taxonomy here means the model self-corrects without interrupting the human, and the loop's existing retry path handles it without special-casing hooks.

**Why does the error classifier emit an event rather than raise?** Raising from inside the error classifier would unwind to a single handler. Emitting a `loop.context_too_long` event lets multiple independent subscribers react: the compactor in spec 12 triggers context compaction, the logger records the classified error, and any adopter-defined subscriber can hook in — all without coupling them to each other. The event bus model is the correct pattern when one cause has multiple orthogonal effects.

**Why does `SteeringQueue.drain()` insert at the TOP of each iteration?** Inserting at the top — before the model call — means the model sees the follow-up note on the very next decision cycle, not buried after accumulated tool results. Inserting between iterations (not inside a tool call) avoids any lock contention with a currently-running tool. The ordering is deterministic: all drained notes appear, in insertion order, before the model call for that iteration.

## Internal loop hooks vs Claude Code hooks

These are distinct integration points. **Spec 06** (`06-hook-integration.md`) describes external shell hooks (`PreToolUse`, `PostToolUse`, `Stop`) that Claude Code fires at the OS process boundary — they receive JSON over stdin and exit with a code. **This spec** describes intra-loop Python hooks (`PreToolHook`, `PostToolHook`) that run inside the `pyarnes_swarm` agent loop as coroutines, with direct access to the live args dict and raw result. Claude Code hooks govern the coding session from outside; loop hooks extend agent behaviour from inside. They coexist: a production configuration can have both.

## PreToolHook and PostToolHook (P4)

Defined as `typing.Protocol` in `pyarnes_swarm.hooks`.

```python
from typing import Any, Protocol

class PreToolHook(Protocol):
    async def __call__(
        self,
        tool_name: str,
        args: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Return modified args to override the call, or None to pass through unchanged.

        Raise LLMRecoverableError to veto the call — the loop feeds the error
        back as a ToolMessage so the model can self-correct.
        """
        ...


class PostToolHook(Protocol):
    async def __call__(
        self,
        tool_name: str,
        result: Any,
        is_error: bool,
    ) -> Any:
        """Return value replaces the result fed into the ToolMessage for that call.

        Returning the unmodified result is valid (and the common case).
        """
        ...
```

`PreToolHook` receives the tool name and the resolved args dict before dispatch. Returning `None` means the args are used as-is. Returning a new dict replaces the args for this call only — the stored message history is not mutated. Raising `LLMRecoverableError` vetoes the dispatch: the loop wraps the error in a `ToolMessage` and continues, giving the model a chance to re-issue a corrected call.

`PostToolHook` receives the tool name, the raw result, and `is_error` (true when the tool itself signalled failure). Its return value is what the loop constructs the `ToolMessage` from. This allows result normalisation, redaction, or enrichment without touching the tool implementation.

Module: `pyarnes_swarm.hooks`

## Error classifier (H5)

Defined in `pyarnes_swarm.hooks.classifier`.

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class ClassifiedError:
    original: Exception
    should_compress: bool    # True when context is the likely cause of the error
```

When `should_compress` is `True`, the classifier emits a `loop.context_too_long` event on the loop's internal event bus. The compactor defined in spec 12 subscribes to this event and triggers context compaction before the next model call. Classifier and compactor are decoupled: the classifier never imports the compactor, and the compactor fires in response to the event regardless of what emitted it.

`ClassifiedError` is emitted (not raised) so that logging, compaction, and any adopter-defined subscribers can all react independently to the same signal.

Module: `pyarnes_swarm.hooks.classifier`

## Steering queue (P7)

Defined in `pyarnes_swarm.hooks.steering`.

```python
from dataclasses import dataclass, field

@dataclass
class SteeringQueue:
    _notes: list[str] = field(default_factory=list, init=False)

    def push(self, note: str) -> None:
        """Enqueue a follow-up note to inject before the next model call."""
        ...

    def drain(self) -> list[str]:
        """Return all queued notes in insertion order and clear the queue.

        Called once per iteration, before the model call. Returns an empty
        list when no notes are pending.
        """
        ...
```

`drain()` is called at the top of each iteration before the model call. The loop prepends each drained note as a `user` message (or an equivalent system-level annotation, per adopter preference) so the model receives them on the next decision cycle. Because `drain()` runs between iterations — never while a tool is executing — there is no lock contention with in-flight tool calls. The queue is single-consumer (the loop) and can be written to from any coroutine, including tool handlers that want to suggest a follow-up action.

Module: `pyarnes_swarm.hooks.steering`

## Integration in LoopConfig

Hook lists and the steering queue are opt-in fields on `LoopConfig`. Omitting them (all default to empty / `None`) produces the existing loop behaviour with zero overhead.

```python
from dataclasses import dataclass, field

@dataclass
class LoopConfig:
    # ... existing fields (max_iterations, max_retries, budget, compaction_config, ...) ...

    pre_tool_hooks: list[PreToolHook] = field(default_factory=list)
    post_tool_hooks: list[PostToolHook] = field(default_factory=list)
    steering: SteeringQueue | None = None
```

The loop applies `pre_tool_hooks` in list order before each tool dispatch. If any hook raises `LLMRecoverableError`, the remaining hooks are skipped and the veto is processed. `post_tool_hooks` run in list order after each tool call; each hook receives the result from the previous hook (or the raw result for the first hook), forming a pipeline. `steering.drain()` is called once per iteration, before the model call, when `steering` is not `None`.
