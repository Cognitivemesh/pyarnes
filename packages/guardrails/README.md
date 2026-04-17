# pyarnes-guardrails

Composable safety guardrails for the pyarnes agentic harness.

## What's included

- **Guardrail ABC** — abstract base for custom guardrail checks
- **PathGuardrail** — block tool calls referencing paths outside allowed roots
- **CommandGuardrail** — block shell commands matching dangerous patterns
- **ToolAllowlistGuardrail** — only permit pre-approved tool names
- **GuardrailChain** — run a sequence of guardrails; fail on the first violation
