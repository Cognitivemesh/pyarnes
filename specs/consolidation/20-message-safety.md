# pyarnes_swarm — Message Safety Pipeline

> **Spec header**
>
> | Field | Value |
> |---|---|
> | **Title** | pyarnes_swarm — Message Safety |
> | **Status** | active |
> | **Type** | integrations-safety |
> | **Owns** | SanitizePipeline (input H6), InjectionGuardrail (output H8), prompt-injection defense, sanitization-vs-guardrail phase ordering |
> | **Depends on** | 04-swarm-api.md |
> | **Extends** | 21-loop-hooks.md |
> | **Supersedes** | — |
> | **Read after** | 06-hook-integration.md |
> | **Read before** | 22-transport.md |
> | **Not owned here** | external hook contract (see `06-hook-integration.md`); internal hook insertion points (see `21-loop-hooks.md`); evaluation semantics (see `07-bench-integrated-axes.md`); transport (see `22-transport.md`) |
> | **Last reviewed** | 2026-04-29 |

## Design Rationale

> **Diagram:** [Sanitize → guardrail pipeline](diagrams/20-sanitize-guardrail.html).

**Why sanitize on a copy, not the stored history?** The stored conversation history must be replayable without sanitization artifacts. If `sanitize_messages()` mutated the history in place, replaying the session from the stored JSONL would produce different model inputs than the original run — defeating audit and debugging. Operating on the copy passed to `model.next_action()` keeps the raw messages intact in storage while ensuring only sanitized content reaches the model.

**Why does `InjectionGuardrail` raise `LLMRecoverableError` and not `UserFixableError`?** Prompt injection is typically a model-generated artifact (the model is about to call a tool with injected instructions). Returning the error as a `ToolMessage` lets the model recognise it made a bad call and self-correct on the next iteration — no human needs to be interrupted. `UserFixableError` is reserved for situations where human judgement is required; a model that produced an injected prompt argument can fix it without help.

**Why is message sanitization a separate module from guardrails?** The intervention points are different. Sanitization happens *before* `model.next_action()` — it shapes the input the model sees. Guardrails fire *after* the model produces a tool call — they veto execution of a tool call that was already decided. These are architecturally separate stages of the loop; putting both in the same module would conflate input filtering with output enforcement and make the intervention order ambiguous.

## Message sanitization (H6)

`sanitize_messages()` is called on the copy passed to `model.next_action()`, not on the stored history. The function is pure — it returns a new list and never mutates its input.

Module: `pyarnes_swarm.safety.sanitize`

```python
from pyarnes_swarm.safety.sanitize import sanitize_messages, SanitizePipeline, Sanitizer

class Sanitizer(Protocol):
    """Single transformation step applied to each message in the history copy."""
    def sanitize(self, message: dict) -> dict:
        """Return a sanitized copy of *message*. Never mutate the input."""
        ...

@dataclass
class SanitizePipeline:
    """Ordered chain of Sanitizer steps applied left-to-right.

    Pass to LoopConfig.sanitize. None means no sanitization (default).
    """
    steps: list[Sanitizer]

    def apply(self, messages: list[dict]) -> list[dict]:
        """Return a new list with each step applied in order. Input is not modified."""
        ...

def sanitize_messages(
    messages: list[dict],
    pipeline: SanitizePipeline,
) -> list[dict]:
    """Apply *pipeline* to a copy of *messages*. Called by the loop before model.next_action().

    The caller retains the original list for history storage; only the returned
    copy reaches the model.
    """
    ...
```

### Integration in the loop

The loop keeps two references: `self._history` (the stored list, never mutated by sanitization) and a local `messages` variable (the copy that may be transformed):

```python
# Inside AgentLoop._run_iteration():
messages_for_model = sanitize_messages(self._history, self._config.sanitize) \
    if self._config.sanitize else list(self._history)
action = await self._model.next_action(messages_for_model)
```

The stored history is appended to as normal after the model responds — the sanitization does not persist.

## Prompt injection defense (H8)

`InjectionGuardrail` sits in the guardrail chain and inspects tool-call arguments for patterns consistent with prompt injection (instruction overrides, role-change directives, ignore-previous-instructions payloads).

Module: `pyarnes_swarm.safety.injection`

```python
from pyarnes_swarm.safety.injection import InjectionGuardrail, InjectionPattern

@dataclass
class InjectionPattern:
    """A single detection pattern (regex or substring) and the error message to raise."""
    pattern: str
    message: str
    is_regex: bool = False

class InjectionGuardrail(Guardrail):
    """Veto tool calls whose arguments contain prompt-injection patterns.

    Raises LLMRecoverableError — the error is returned as a ToolMessage so the
    model self-corrects without interrupting the human operator.

    Default patterns cover common injection templates (ignore/override/role-change).
    Supply custom_patterns to extend or replace the defaults.
    """
    def __init__(
        self,
        custom_patterns: list[InjectionPattern] | None = None,
        replace_defaults: bool = False,
    ) -> None: ...

    def check(self, tool_name: str, arguments: dict) -> None:
        """Raise LLMRecoverableError if any argument value matches an injection pattern."""
        ...
```

### Behaviour on detection

When a pattern matches, `InjectionGuardrail.check()` raises `LLMRecoverableError`. The loop catches it, wraps it in a `ToolMessage(is_error=True, content=<error text>)`, and appends it to the history so the model sees its own mistake and can retry with clean arguments.

```python
# Usage — wire into GuardrailChain:
from pyarnes_swarm.safety.injection import InjectionGuardrail
from pyarnes_swarm.guardrails import GuardrailChain, PathGuardrail

guardrails = GuardrailChain([
    PathGuardrail(allowed_roots=("./workspace",)),
    InjectionGuardrail(),               # default patterns
])
```

## Integration in `LoopConfig`

Both safety features are opt-in and default to `None` — existing users see zero behaviour change.

```python
@dataclass
class LoopConfig:
    max_iterations: int = 10
    max_retries: int = 2
    budget: IterationBudget | None = None
    compaction_config: MessageCompactorConfig | None = None
    reflection_interval: int | None = None
    sanitize: SanitizePipeline | None = None       # H6: applied to copy before model call
    injection_guard: InjectionGuardrail | None = None  # H8: added to guardrail chain automatically
```

`injection_guard` is a convenience shortcut: when set on `LoopConfig`, the runtime appends it to the `GuardrailChain` before the first iteration. It is equivalent to adding `InjectionGuardrail()` to the chain manually — the shortcut exists so adopters can enable injection defense without rewriting their guardrail setup.
