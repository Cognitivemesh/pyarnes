# TDD — Red / Green / Refactor

Follow the strict TDD cycle for every change:

## 🔴 Red — Write a failing test first

1. Identify the **smallest** behaviour to implement next.
2. Write a test in `tests/unit/` (or `tests/features/` for BDD) that captures that behaviour.
3. Run `uv run tasks test` — the new test **must fail**.
4. If the test passes immediately, the test is not adding value — tighten it.

## 🟢 Green — Make it pass with the simplest code

1. Write the **minimum** production code in `packages/<name>/src/` to make the failing test pass.
2. Run `uv run tasks test` — all tests **must pass**.
3. Do not add features, optimisations, or abstractions yet.

## 🔵 Refactor — Clean up while green

1. Improve naming, extract helpers, remove duplication — but only while tests stay green.
2. Run `uv run tasks check` (lint + typecheck + test) after every refactor step.
3. Commit when the refactor is clean.

## Workflow tips

- Use `uv run tasks watch` for continuous test execution.
- Keep commits small: one Red-Green-Refactor cycle per commit.
- Prefer `pytest.mark.parametrize` for table-driven tests.
- Use `pytest-bdd` with `.feature` files for acceptance-level specs.
