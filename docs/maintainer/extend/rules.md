---
persona: maintainer
level: L2
tags: [maintainer, extend, rules]
---

# Extension rules

Rules of thumb for contributors adding new surfaces without breaking adopters.

## Rule 0 — no CLI in `pyarnes-harness`

`pyarnes-harness` is a library. Do not add `click`, `typer`, argparse, or any other CLI framework to its dependency graph. Worked-example CLIs belong in the adopter project's own code (scaffolded via the Copier template), not in the pyarnes monorepo.

## Adding a new `Guardrail` subclass

1. Code lives under `packages/guardrails/src/pyarnes_guardrails/`. If it's general-purpose (adopter-agnostic), add it to `guardrails.py`. If it belongs to one adopter pattern, add it under that adopter's `guardrails.py` instead.
2. Export general-purpose guardrails from `packages/guardrails/src/pyarnes_guardrails/__init__.py` — add the class name to `__all__` and update `CHANGELOG.md` under `## [Unreleased] → Added`.
3. Add the class to `STABLE_SURFACE["pyarnes_guardrails"]` in `tests/unit/test_stable_surface.py`.
4. Add an example to `docs/maintainer/packages/guardrails.md § Public API` showing the `check(tool_name, arguments)` contract.
5. Write a unit test in `tests/unit/test_guardrails.py` covering (a) the blocking case with `UserFixableError` and (b) the pass-through case where the guardrail does not apply.

## Adding a new `Scorer` subclass

Same pattern as guardrails. `pyarnes-bench` is small on purpose — think twice before adding a new scorer. If it belongs to a single adopter (e.g. a domain-specific similarity metric), keep it out of the library and ship it inside that adopter's `tests/bench/` instead.

## Adding a new `pyarnes-tasks` subcommand

1. Register the task in `packages/tasks/src/pyarnes_tasks/cli.py`.
2. Add it to the task table in `docs/adopter/build/tasks.md`.
3. Respect the two quirks: missing paths are silently dropped; pytest exit code 5 ("no tests collected") is treated as success for the `test` / `test:cov` tasks.
4. Keep it pure subprocess orchestration — the task runner should not import runtime packages like `pyarnes-harness`.

## Adding a new reference adopter

pyarnes does not ship `packages/example-*` in-tree — reference adopters live as specs under [`specs/`](https://github.com/Cognitivemesh/pyarnes/tree/main/specs) and are selected via the Copier `adopter_shape` question. To add a new one:

1. Write the spec as `specs/NN-adopter-<shape>.md` (numbering follows the existing `specs/03-examples-adopter-a-and-b.md` and `specs/04-template-adopter-c-meta-use.md`). Cover: pipeline shape, which pyarnes surfaces it uses, guardrails/scorers it requires, and conditional template files.
2. Add the shape to the `adopter_shape` choices in `copier.yml`.
3. If the shape needs shape-specific template files, add them under `template/` with Jinja conditions keyed on `adopter_shape`. Use `_exclude` in `copier.yml` for files that should only ship to that shape (mirrors how `enable_dev_hooks` and `enable_code_graph` are handled).
4. Extend `tests/template/test_scaffold.py` with a new parameterisation asserting the shape generates the expected files + deps.
5. Document the adopter in `docs/adopter/evaluate/distribution.md` alongside the existing three.

## Adding a new public symbol

Checklist before merging:

- [ ] Export from the package `__init__.py` via `__all__`.
- [ ] Add to `CHANGELOG.md → ## [Unreleased] → Added`.
- [ ] Add to `STABLE_SURFACE` in `tests/unit/test_stable_surface.py`.
- [ ] Mention in the owning package's deep-dive under `docs/maintainer/packages/` (add to its `## Public API` section).
- [ ] Ship with at least one unit test plus, if the symbol is user-facing behaviour, a Gherkin feature under `tests/features/`.

## What to leave private

Anything whose name starts with `_`. Log event strings. JSONL field order. Concrete types of `Lifecycle.history`. See the private-surface list in `CHANGELOG.md` for the canonical inventory.

## See also

- [Evolving workflow](workflow.md) — step-by-step procedures for adding packages and specs.
- [Release workflow](../release.md) — how the stable-surface checklist is enforced in CI.
