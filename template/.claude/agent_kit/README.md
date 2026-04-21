# agent_kit — scaffolding for agent skills and tools

These files are **reference templates** your AI coding agent (Claude Code,
Cursor, Codex) adapts when you ask it to add agent-loop features — pipelines,
tool handlers, guardrails — to this project.

They are **not** imported by runtime code in `src/`. They import
`pyarnes_harness`, `pyarnes_guardrails`, and `pyarnes_core` from
`[dependency-groups.dev]`, so they only resolve in a `uv sync`-ed dev
environment.

## What's here

- `pipeline.py` — reference `AgentLoop` builder (registry + chain + loop).
  Copy / adapt when you scaffold a real pipeline.
- `guardrails.py` — example `Guardrail` subclasses wired into a
  `GuardrailChain`. Extend with project-specific rules.
- `tools/__init__.py` — example `ToolHandler` subclasses with shape-specific
  stubs.

## When your AI agent asks "where should this live?"

- **Production code** (imported by `{{ project_module }}.cli` or other `src/`
  modules) → `src/{{ project_module }}/`. No pyarnes imports there.
- **Agent-loop scaffolding** (things wired into the harness / guardrail
  chain, used only during dev or behind an explicit `pyarnes` extra) →
  here, `.claude/agent_kit/`.
- **Shape-specific library demos** (standalone kreuzberg / boto3 / httpx
  scripts) → `scripts/examples/<shape>/` with PEP 723 inline metadata.
