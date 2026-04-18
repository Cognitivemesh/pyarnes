# specs — Feature specifications

This directory holds **specifications for pyarnes features** — one Markdown file per feature, drafted before (or alongside) the PR that implements it.

Treat a spec as the **contract between design and implementation**: the motivation, the shape of the API, the tests that will prove it works, and the open questions the author wants to flag.

## What goes here

- Proposed new functionality for any of the five `pyarnes-*` packages.
- Breaking changes and their migration story.
- Template changes that alter the developer experience (prompt shape, bootstrap flow, defaults).
- Anything large enough that writing it down up front beats iterating in PR review.

## What does **not** go here

- Bug-fix notes — the PR description is the right home for those.
- Meeting minutes / decision logs — keep those in an issue or a team notes doc.
- End-user documentation — that lives under [`docs/`](../docs/).

## File naming

Use a short, descriptive, hyphenated lowercase name. Prefix with the package or area it touches:

- `core-capability-tokens.md`
- `harness-tool-timeouts.md`
- `guardrails-regex-engine.md`
- `template-multi-python-support.md`

## Minimum spec shape

Every spec should cover:

1. **Context** — what problem are we solving, and why now?
2. **Goals / non-goals** — what counts as success, what's explicitly out of scope.
3. **Proposed design** — the public API, the internal changes, example usage.
4. **Tests / acceptance** — the concrete behaviours a reviewer should expect to see tested.
5. **Open questions** — what's still undecided.

## Excluded from generated projects

This folder lives only in the pyarnes monorepo. When a developer bootstraps a new project with `uvx copier copy gh:Cognitivemesh/pyarnes …`, `specs/` is **not** copied — it's explicitly excluded in `copier.yml` and it sits outside the `template/` subtree that Copier reads from.
