---
mode: agent
description: 'Run a full Red-Green-Refactor TDD cycle. Provide the behaviour to implement and this prompt guides the complete test-first workflow.'
---

# TDD Cycle for pyarnes

Implement `$BEHAVIOUR` using strict Red-Green-Refactor.

## Step 1 — Red: Write a failing test

1. Identify the smallest testable unit of `$BEHAVIOUR`.
2. Create the test in `tests/unit/test_<module>.py` (or `tests/features/<name>.feature` for BDD).
3. Run `uv run tasks test` and confirm the new test **fails**.

## Step 2 — Green: Minimal passing code

1. Write the minimum production code in `packages/<name>/src/` to make the test pass.
2. Run `uv run tasks test` — **all tests must pass** before proceeding.

## Step 3 — Refactor: Clean while green

1. Improve naming, remove duplication, extract helpers only if it reduces complexity.
2. After each change, run `uv run tasks check`.
3. Stop when the code is clean and all checks pass.

## Commit

Commit with message: `feat(<package>): <one-line description of the behaviour>`

## Commands reference

```bash
uv run tasks test     # run tests
uv run tasks watch    # continuous TDD loop
uv run tasks check    # lint + typecheck + test
uv run tasks format   # auto-format
```
