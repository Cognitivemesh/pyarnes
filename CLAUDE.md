# Pyarnes — Project Instructions

## What is this?

A minimal agentic harness engineering template. It does **not** replace Claude Code, Cursor, or Codex — it **collaborates** with them by adding verification loops, safety enforcement, and lifecycle management that these tools lack.

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## Quick commands

```bash
uv run tasks help        # list all tasks
uv run tasks test        # run tests
uv run tasks check       # lint + typecheck + test
uv run tasks watch       # TDD watch mode
uv run tasks format      # auto-format
uv run tasks lint        # ruff lint
uv run tasks security    # bandit security scan
uv run tasks radon:cc    # cyclomatic complexity
uv run tasks vulture     # dead code detection
uv run tasks complexity  # radon:cc + radon:mi
uv run tasks docs:serve  # local docs site
```

## Error taxonomy

| Type | Behaviour |
|---|---|
| `TransientError` | Retry with exponential backoff (cap: 2) |
| `LLMRecoverableError` | Return as ToolMessage so the model adjusts |
| `UserFixableError` | Interrupt for human input |
| `UnexpectedError` | Bubble up for debugging |

## Key architecture (monorepo)

- `packages/core/` — **pyarnes-core**: types, errors, lifecycle, observe/logging
- `packages/harness/` — **pyarnes-harness**: loop, tools, capture
- `packages/guardrails/` — **pyarnes-guardrails**: composable safety guardrails
- `packages/bench/` — **pyarnes-bench**: evaluation and benchmarking toolkit
- `packages/tasks/` — **pyarnes-tasks**: cross-platform task runner (the `tasks` CLI)
- `tests/unit/` — unit tests
- `tests/features/` — BDD feature files (pytest-bdd / Gherkin)
- `docs/` — MkDocs Material documentation source
- `template/` + `copier.yml` — Copier template used by `uvx copier copy gh:Cognitivemesh/pyarnes <dest>`
  to scaffold new projects that depend on pyarnes packages via git URLs.

## Conventions

- All code is **async-first** (asyncio) to avoid GIL contention.
- Logging goes to **stderr** as JSONL via **loguru**; stdout is reserved for tool results.
- Docstrings follow **PEP 257** conventions (Google style).
- Use `uv run tasks tdd` workflow: Red → Green → Refactor.
- Types are enforced via `ruff` + `ty`.

## Functional utilities (included, use them)

| Library | When to use |
|---|---|
| `returns` | Explicit error paths — wrap risky operations in `Result`/`Maybe` instead of bare `try/except` |
| `toolz` | Data transformation pipelines — `pipe(data, step1, step2)`, `compose`, `curry` |
| `funcy` | Collection helpers — `lmap`, `lfilter`, `chunks`, `take`, `distinct` on tool result lists |
| `more-itertools` | Advanced iteration — `batched`, `windowed`, `flatten` for streaming tool outputs |
