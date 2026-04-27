---
persona: adopter
tags: [adopter, evaluate, security]
---

# Security & threat model

pyarnes is a harness, not a full security boundary. Assume an untrusted model can emit arbitrary tool calls and arguments, then design for containment and auditability.

## What pyarnes does **not** protect against by default

### `PathGuardrail` does not resolve symlinks today

The current default path checks use `PurePosixPath` semantics and lexical containment checks. They do not resolve runtime symlinks to filesystem targets (see [issue #11](https://github.com/Cognitivemesh/pyarnes/issues/11)).  
Implication: a path that appears inside an allowed root lexically may still escape at execution time if symlinks are involved.

### `CommandGuardrail` is a denylist of exactly four patterns

`CommandGuardrail.blocked_patterns` currently ships only four regexes (`rm -rf /`, `sudo`, `chmod 777`, `curl | sh`) in [`packages/guardrails/src/pyarnes_guardrails/guardrails.py`](https://github.com/Cognitivemesh/pyarnes/blob/main/packages/guardrails/src/pyarnes_guardrails/guardrails.py#L85-L90). This is a minimal denylist, not a complete command safety policy.

### Misconfiguration can widen blast radius quickly

If guardrails are not wired before tool execution, if `allowed_roots` are too broad, or if command/path argument keys are incomplete, unsafe calls can pass through. pyarnes does not auto-wrap tools for you.

## Hardening guidance

1. Prefer fail-closed posture with `ToolAllowlistGuardrail`.
2. Keep `allowed_roots` narrow and tool-specific.
3. Extend `command_keys` and `blocked_patterns` for your real command surface.
4. Add OS/container sandboxing and egress controls outside pyarnes.
5. Log and audit all tool calls; alert on blocked/near-miss events.

## Security reporting and policy

For disclosure and coordinated fixes, see [SECURITY.md](https://github.com/Cognitivemesh/pyarnes/blob/main/SECURITY.md).
