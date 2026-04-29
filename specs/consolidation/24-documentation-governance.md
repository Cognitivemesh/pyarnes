# pyarnes_swarm — Documentation Governance

> **Spec header**
>
> | Field | Value |
> |---|---|
> | **Title** | pyarnes_swarm — Documentation Governance |
> | **Status** | active |
> | **Type** | governance |
> | **Owns** | docs-site audience split, adopter-onboarding entry pages, contributor-evolution entry pages, semver discoverability strategy |
> | **Depends on** | 18-api-surface-governance.md (semver policy), 19-template-version-control.md (`pyarnes_ref` pinning) |
> | **Extends** | — |
> | **Supersedes** | the "Distribution and documentation" section formerly inside 00-overview.md |
> | **Read after** | 00-overview.md |
> | **Read before** | — |
> | **Not owned here** | the runtime program plan (00-overview.md), library API surface (07-swarm-api.md, 18-api-surface-governance.md), template versioning policy (19-template-version-control.md) |
> | **Last reviewed** | 2026-04-29 |

## Why this spec exists

Distribution and documentation strategy is a different document from the runtime program plan, with a different audience (docs-site readers, not runtime adopters writing their first CLI). It used to live inside `00-overview.md` and got tangled with OKRs, design principles, and migration tables. This spec extracts it so each document answers one reader-question.

## Audience split

The docs site has two distinct audiences with separate entry paths:

- **Adopters** — teams building a product that uses `pyarnes_swarm` as a runtime dependency. They need to know which symbols are stable, how to scaffold a project with Copier, and how to wire the three-part contract (register tools → compose guardrails → run the loop). They should never need to read the API reference to scaffold their first working CLI.
- **Contributors** — engineers evolving `pyarnes_swarm` itself. They need to know the semver policy, how to add a new `Guardrail` or `Scorer` without breaking downstream pins, and how to evolve the Copier template safely.

Each audience has its own entry page; cross-links between the two are explicit, never implicit.

## `docs/getting-started/distribution.md`

The canonical adopter onboarding page. Covers:

- The distribution recommendation in one sentence: library-first, adopter owns the CLI, `pyarnes-tasks` is dev-only.
- The three-phase model: **bootstrap** (scaffold via Copier) → **develop** (write tools / guardrails, run `uv run tasks check`) → **run** (ship the adopter's own CLI).
- The full adopter / package inventory table showing which `pyarnes_swarm` symbol or sub-module enters at each phase.
- `pyarnes_ref` pinning strategy (owned by [19-template-version-control.md](19-template-version-control.md)): default `main` for bleeding-edge; pin to a tag once the first stable release lands; bump via `uv sync` after updating `pyarnes_ref`.
- Cross-reference to `docs/template.md` for the full Copier walkthrough.

## `docs/architecture/meta-use.md`

The Adopter C (rtm-toggl-agile) pattern page. Covers:

- Why `pyarnes_swarm` appears twice in this shape: shipped runtime + dev-time coding-agent harness.
- Full hook code (imported from `template/.claude/hooks/` to stay in sync rather than duplicated).
- The lifecycle-per-branch pattern: each git branch gets its own `.pyarnes/` JSONL stream so parallel feature branches don't interleave audit logs.
- `.pyarnes/` directory layout (mirrors the layout in [10-hook-integration.md](10-hook-integration.md)).
- How the bench corpus is structured: `tests/bench/scenarios/*.yaml` labelled fixtures, `EvalSuite` + `DiffSimilarityScorer` / `TestsPassScorer`, minimum `pass_rate >= 0.80` assertion.
- Cross-reference to `tests/bench/test_agent_quality.py.jinja` from [10-hook-integration.md](10-hook-integration.md).

## Semver policy discoverability

Semver policy is owned by [18-api-surface-governance.md](18-api-surface-governance.md) (stable API surface tables and breaking-change rules). The docs surface this through two entry points:

- `docs/getting-started/distribution.md` links to `docs/development/release.md` for adopters who want to understand the pinning contract.
- `docs/development/evolving.md` includes the "Stable API surface" section (full tables from [18-api-surface-governance.md](18-api-surface-governance.md)) and the breaking-change policy for contributors.

## Open follow-ups (filed during 00-overview reorg)

These came out of the Phase-2 audit during the 00-overview reorg and need handling under this spec or its dependencies, _not_ in 00-overview itself:

| Issue | Owner spec |
|---|---|
| The Copier template still imports `pyarnes_core / pyarnes_harness / pyarnes_guardrails` instead of `pyarnes_swarm` (`template/.claude/agent_kit/pipeline.py.jinja`). Inconsistent with single-package goal. | [19-template-version-control.md](19-template-version-control.md) |
