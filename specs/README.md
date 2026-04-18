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

Multi-PR rollouts of a single feature use a `PR-NN-<slug>.md` naming scheme and include a feature-level README entry below.

## Minimum spec shape

Every spec should cover:

1. **Context** — what problem are we solving, and why now?
2. **Goals / non-goals** — what counts as success, what's explicitly out of scope.
3. **Proposed design** — the public API, the internal changes, example usage.
4. **Tests / acceptance** — the concrete behaviours a reviewer should expect to see tested.
5. **Open questions** — what's still undecided.

## Excluded from generated projects

This folder lives only in the pyarnes monorepo. When a developer bootstraps a new project with `uvx copier copy gh:Cognitivemesh/pyarnes …`, `specs/` is **not** copied — it's explicitly excluded in `copier.yml` and it sits outside the `template/` subtree that Copier reads from.

---

## Current feature rollouts

### Distribution strategy (01 → 05)

Sequential specs decomposing the approved "library-first, adopter owns the CLI, pyarnes-tasks is dev-only" plan into reviewable PR-sized chunks.

| #  | Spec                                                                                         | Ships                                                                   | Depends on |
|----|----------------------------------------------------------------------------------------------|-------------------------------------------------------------------------|------------|
| 01 | [`01-core-stable-api-surface.md`](01-core-stable-api-surface.md)                             | `CHANGELOG.md` + semver policy + `tests/unit/test_stable_surface.py`    | —          |
| 02 | [`02-template-adopter-scaffold.md`](02-template-adopter-scaffold.md)                         | Copier `adopter_shape` + starter pipeline/cli/tools/guardrails          | 01         |
| 03 | [`03-examples-adopter-a-and-b.md`](03-examples-adopter-a-and-b.md)                           | Design rationale for the `pii-redaction` + `s3-sweep` template shapes   | 01, 02     |
| 04 | [`04-template-adopter-c-meta-use.md`](04-template-adopter-c-meta-use.md)                     | `rtm-toggl-agile` shape + `.claude/hooks/` + bench scaffold             | 01, 02, 03 |
| 05 | [`05-docs-distribution-and-meta-use.md`](05-docs-distribution-and-meta-use.md)               | `distribution.md` + `meta-use.md` + contributor guides + nav update     | 01–04      |

### Code-graph feature (PR-01 → PR-06)

Sequential PR specs that deliver the code-graph feature end-to-end. Implement strictly in order; each PR has hard dependencies on the previous ones.

| PR  | Spec                                                                                         | Ships                                                                  | Depends on   |
|-----|----------------------------------------------------------------------------------------------|------------------------------------------------------------------------|--------------|
| 01  | [`PR-01-graph-package-foundation.md`](PR-01-graph-package-foundation.md)                     | `packages/graph/` + SQLModel schema + async Turso engine + repository   | —            |
| 02  | [`PR-02-extractor-and-indexer.md`](PR-02-extractor-and-indexer.md)                           | Tree-sitter extractor + SHA-256 incremental indexer + `# WHY` comments  | PR-01        |
| 03  | [`PR-03-analytics-and-report.md`](PR-03-analytics-and-report.md)                             | Blast-radius / centrality / communities + `GRAPH_REPORT.md` generator   | PR-02        |
| 04  | [`PR-04-tools-mcp-and-hook.md`](PR-04-tools-mcp-and-hook.md)                                 | Four `ToolHandler` subclasses + stdio MCP server + PreToolUse hook      | PR-03        |
| 05  | [`PR-05-eval-and-usage-tracking.md`](PR-05-eval-and-usage-tracking.md)                       | `TokenReductionScorer` + `LLMJudgeScorer` + usage tracker + `graph:ci`  | PR-02, PR-04 |
| 06  | [`PR-06-skills-template-docs.md`](PR-06-skills-template-docs.md)                             | `/overview` `/impact` `/patch` `/ship` skills + template + docs         | PR-04, PR-05 |

Each PR spec adds the following sections beyond the minimum above:

- **Reuse** — existing pyarnes utilities leveraged (no reinvention).
- **Risks & rollback** — what can go wrong and how to undo.
- **Exit criteria** — the gate each PR must pass before the next one starts.

The overarching design — token-reduction target (5×-71×), Turso-backed storage, SQLModel schema, error-taxonomy mapping, reuse map — is captured in the parent plan file. These specs are the executable decomposition of that plan.
