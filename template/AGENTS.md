# AGENTS.md — Behavioral Contract for AI Agents

This file defines what AI coding agents (Claude Code, Cursor, Codex, etc.) are
expected to do — and not do — when working in this project.

Agents that read this file should treat it as a binding policy, not a suggestion.

Shape-specific tech integrations (kreuzberg / boto3 / httpx / pydantic …)
belong in `scripts/examples/<shape>/` as **PEP 723** scripts. Do not add
them to `src/` or `[project.dependencies]` — they are illustrative demos,
not project-wide runtime deps.

---

## Allowed actions (no confirmation needed)

- Read any file in the repository.
- Edit source files under `src/`, `tests/`, `docs/`.
- Run `uv run tasks check`, `uv run tasks test`, `uv run tasks lint`.
- Create new files following existing conventions.
- Propose changes via a branch + PR.

## Actions that require explicit user confirmation

- **Push to `main`** — always ask before `git push origin main`.
- **Force-push** — never force-push without explicit instruction.
- **Destructive file operations** — `rm`, `rmdir`, overwriting without reading first.
- **Network requests** — curl, wget, or any outbound HTTP call in tool code.
- **Installing packages** — `uv add` or `pip install` modifies the lockfile; confirm first.
- **Running shell commands with elevated permissions** — no `sudo`.

## Code quality contract

Every code change must:

1. Pass `uv run tasks check` (lint + typecheck + test) before being committed.
2. Follow async-first conventions — use `async def` and `await` throughout.
3. Add or update tests for every new public function or class.
4. Export new public symbols from the package `__init__.py` `__all__`.
5. Not introduce `eval`, `exec`, `compile`, `subprocess`, or `ctypes` imports
   without an explicit security review comment explaining why it is safe.

## Safety guardrails

`pyarnes-guardrails` is a dev-time dependency. When scaffolding agent
features under `.claude/agent_kit/`, tool handlers must:

- Wrap file-access tools with `PathGuardrail(allowed_roots=("/workspace",))`.
- Wrap shell-execution tools with `CommandGuardrail()`.
- Use `Path.resolve() + is_relative_to()` — never `str.startswith()` — for
  path containment checks.
- Use `analyse_code` / `scan_code_arguments` from `pyarnes_core.safety` when
  a tool accepts Python source code as an argument.

## Error handling contract

These error types are imported from `pyarnes_core.errors` by code under
`.claude/agent_kit/` and `.claude/hooks/`. When writing plain code under
`src/`, use standard Python exceptions unless you explicitly add pyarnes
as a runtime dep.

| Condition | Error to raise |
|---|---|
| Network timeout, rate-limit | `TransientError` |
| Model produced an invalid action | `LLMRecoverableError` |
| Path outside workspace, blocked command | `UserFixableError` |
| Truly unexpected failure | `UnexpectedError` |

## What agents should NOT do

- Silence linter or test failures with `# noqa`, `# type: ignore`, or
  `pytest.mark.skip` without explaining why.
- Expand scope beyond what the task requires.
- Commit partial implementations — keep the test suite green at every commit.
- Add `print()` statements to production code; use `logger.info(...)` from
  `loguru` (or `pyarnes_core.observe` when writing agent scaffolding under
  `.claude/agent_kit/`).
