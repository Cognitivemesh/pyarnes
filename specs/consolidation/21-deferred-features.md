# pyarnes_swarm — Deferred / Historical Absorption Map

> **Spec header**
>
> | Field | Value |
> |---|---|
> | **Title** | pyarnes_swarm — Deferred / Historical Absorption Map |
> | **Status** | appendix |
> | **Type** | historical-appendix |
> | **Tags** | roadmap, deferred, planning |
> | **Owns** | mapping of absorbed legacy specs (PR-01..PR-06, harness-feature-expansion, etc.) to their canonical consolidation homes |
> | **Depends on** | 00-overview.md |
> | **Extends** | — |
> | **Supersedes** | — |
> | **Read after** | — |
> | **Read before** | — |
> | **Not owned here** | every active concept — this appendix owns only the legacy-spec → consolidation-target mapping; see `00-overview.md` inventory for canonical owners |
> | **Last reviewed** | 2026-04-29 |

## Design Rationale

> **Note:** All features previously listed here as "deferred" have been absorbed into the consolidation specs. This file is preserved as a historical pointer.

This appendix keeps the legacy-spec to consolidation-target mapping after the
original source files were removed from the tree.

## Specification

### Absorbed legacy specs

The following original specs have been absorbed:

- `PR-01-graph-package-foundation.md` through `PR-06-skills-template-docs.md` → `20-graph-package.md`
- `harness-feature-expansion.md` → `11-message-safety.md` (Phase 1), `09-loop-hooks.md` (Phase 2), `08-token-budget.md` (Phase 3), `12-transport.md` (Phase 4), `07-swarm-api.md` + `16-run-logger.md` (Phase 5), and `14-secrets.md` (credential redaction).
- `claudecode-pyarnes-judge-plugin.md` → absorbed into `10-hook-integration.md` and noted in `23-claude-judge-plugin.md`.

The original source files have been removed from the repository as part of the consolidation cleanup. Their full text is recoverable from git history if needed for historical reference.
