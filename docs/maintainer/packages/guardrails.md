---
persona: maintainer
level: L2
tags: [maintainer, packages, guardrails]
---

# pyarnes-guardrails

Composable safety checks that run before a tool executes. A guardrail is any object with `check(tool_name, arguments) -> None` — raise `UserFixableError` to block, return silently to allow.

## Module layout

Inter-package deps live in [Architecture § Package graph](../extend/architecture.md#package-graph). Single-file package by design — guardrails are small, composable, and belong together.

| Symbol | Role |
|---|---|
| `Guardrail` | ABC with one method: `check(tool_name, arguments)`. |
| `PathGuardrail` | Blocks paths outside allowed roots. |
| `CommandGuardrail` | Blocks shell commands matching dangerous regex patterns. |
| `ToolAllowlistGuardrail` | Blocks tools not in an allowlist. |
| `GuardrailChain` | Runs a list of guardrails in order; first violation short-circuits. |

## Why this package exists

Repo-wide rules live in [Architecture § Cross-cutting design principles](../extend/architecture.md#cross-cutting-design-principles). Package-specific reasons:

- **Safety is a chain, not a switch.** Adopters compose what they need — path+command for a code-editing agent, tool-allowlist for a research agent, custom guardrails for domain policies.
- **One error type, routed.** Every guardrail signals with `UserFixableError` from `pyarnes-core` — the loop already knows how to route it. No bespoke "blocked" shape.
- **Stateless by default.** Each guardrail holds its config (allowed roots, regex list, allowlist set). No session state, no singletons. Testable in isolation.
- **Tool-call shaped, not function-call shaped.** `check(tool_name, arguments)` matches what the loop already has in hand — no adapter layer between the LLM-produced tool call and the safety gate.

## Key flows

### Chain evaluation

```mermaid
sequenceDiagram
    participant Loop as AgentLoop
    participant Chain as GuardrailChain
    participant P as PathGuardrail
    participant C as CommandGuardrail
    participant T as ToolAllowlistGuardrail

    Loop->>Chain: check("shell", {"command": "ls /etc", "path": "/etc"})
    Chain->>P: check(...)
    alt path is /etc and /etc not in allowed_roots
        P-->>Chain: raise UserFixableError
        Chain-->>Loop: raise (short-circuit)
    else allowed
        P-->>Chain: None
        Chain->>C: check(...)
        alt command matches dangerous pattern
            C-->>Chain: raise UserFixableError
            Chain-->>Loop: raise
        else safe
            C-->>Chain: None
            Chain->>T: check(...)
            alt tool not in allowlist
                T-->>Chain: raise UserFixableError
                Chain-->>Loop: raise
            else allowed
                T-->>Chain: None
                Chain-->>Loop: None (pass)
            end
        end
    end
```

Order matters. Put the cheapest / broadest guardrail first.

### Custom guardrail lifecycle

```mermaid
sequenceDiagram
    actor Adopter
    participant MyGuardrail as MyDomainGuardrail<br/>(Guardrail subclass)
    participant Chain as GuardrailChain
    participant Loop as AgentLoop

    Adopter->>MyGuardrail: __init__(config)
    Adopter->>Chain: GuardrailChain([PathGuardrail(...), MyGuardrail, ...])
    Adopter->>Loop: AgentLoop(..., guardrail_chain=chain)
    Loop->>Chain: check(tool, args)
    Chain->>MyGuardrail: check(tool, args)
    MyGuardrail-->>Chain: None | raise UserFixableError
```

Subclasses get the same routing — no guardrail-specific plumbing.

## Public API

### Guardrail ABC

```python
def check(self, tool_name: str, arguments: dict[str, Any]) -> None:
    """Raise UserFixableError if the call violates this guardrail."""
```

Safe calls return `None`. Dangerous calls raise `UserFixableError` with a human-readable message and prompt hint.

### PathGuardrail

Blocks tool calls that reference paths outside allowed root directories.

| Field | Default | Description |
|---|---|---|
| `allowed_roots` | `("/workspace",)` | Directory prefixes that tools may access |
| `path_keys` | `("path", "file", "directory", "target")` | Argument keys expected to contain file paths |

```python
g = PathGuardrail(allowed_roots=("/workspace", "/tmp"))
g.check("read_file", {"path": "/workspace/src/main.py"})  # OK
g.check("read_file", {"path": "/etc/passwd"})  # raises UserFixableError
```

### CommandGuardrail

Blocks shell commands matching dangerous regex patterns.

| Default blocked patterns |
|---|
| `rm -rf /` |
| `sudo` |
| `chmod 777` |
| `curl ... \| sh` |

### ToolAllowlistGuardrail

Only permits pre-approved tool names. If `allowed_tools` is empty, all tools are allowed.

```python
g = ToolAllowlistGuardrail(allowed_tools=frozenset({"echo", "read_file"}))
g.check("echo", {})         # OK
g.check("delete_all", {})   # raises UserFixableError
```

### GuardrailChain

Composes multiple guardrails. Runs them in order; first violation stops the chain.

```python
chain = GuardrailChain(guardrails=[
    PathGuardrail(allowed_roots=("/workspace",)),
    CommandGuardrail(),
    ToolAllowlistGuardrail(allowed_tools=frozenset({"shell", "read_file"})),
])
chain.check("shell", {"command": "ls -la", "path": "/workspace/src"})
```

## Extension points

- **Domain guardrail:** subclass `Guardrail`, implement `check()`. Example: a `VerificationCompleteGuardrail` that blocks `delete_bucket` until a `VerifyStore.is_complete(bucket)` flag flips. Drop it into a chain — no registration needed.
- **Pattern-based variants:** extend `CommandGuardrail` to take additional regexes; do not re-parse args elsewhere.
- **Argument normalisation:** if your tool names differ from Claude Code's, subclass the guardrail and normalise in `check()` before the pattern match.

## Hazards / stable surface

- `Guardrail`, `PathGuardrail`, `CommandGuardrail`, `ToolAllowlistGuardrail`, `GuardrailChain` — stable API; renames are breaking.
- Default patterns in `CommandGuardrail` are additive-only — removing a pattern weakens security for every existing adopter. Add to the list; don't subtract.
- `PathGuardrail.path_keys` — the default tuple is the union of keys Claude Code, Cursor, and Codex use. Extending is safe; shrinking is breaking.
- All guardrails raise `UserFixableError`. Changing to a different error class reroutes every caller's error handler — don't.

The meta-use pattern (`template/.claude/hooks/pyarnes_pre_tool.py`) depends on `GuardrailChain.check` being synchronous and cheap — do not make it async or add I/O.

## See also

- [Extension rules](../extend/rules.md) — new built-in guardrail criteria.
- [Architecture & meta-use](../extend/architecture.md) — how hooks wire a chain around the coding agent itself.
- [pyarnes-core](core.md) — `UserFixableError` that every guardrail raises.
