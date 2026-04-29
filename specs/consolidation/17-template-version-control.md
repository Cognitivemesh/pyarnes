# 17-template-version-control

> **Spec header**
>
> | Field | Value |
> |---|---|
> | **Title** | pyarnes_swarm — Template Version Control |
> | **Status** | active |
> | **Type** | governance |
> | **Owns** | Copier template evolution policy, adopter migration rules, copier.yml versioning, template-level breaking-change handling |
> | **Depends on** | 06-hook-integration.md, 16-api-surface-governance.md |
> | **Extends** | — |
> | **Supersedes** | — |
> | **Read after** | 16-api-surface-governance.md |
> | **Read before** | — |
> | **Not owned here** | external hook contract (see `06-hook-integration.md`); api-surface stability (see `16-api-surface-governance.md`); package structure (see `01-package-structure.md`) |
> | **Extended by** | 15-tooling-artifacts.md |
> | **Last reviewed** | 2026-04-29 |

> See also `06-hook-integration.md` § Adopter shapes (Copier template) — full adopter shapes and dev-time hook details.

## Template Version Control

The pyarnes framework relies on Copier for scaffolding new adoptions. Managing updatability and structure shapes across adoptions is critical.

### `_migrations` Placeholder
To handle evolutionary updates when adopters run `copier update`, the template includes a `_migrations` system. By tracking structure changes in a robust migration path, adopters can seamlessly evolve their projects without destructive diff overwrites on business logic.

### `adopter_shape` Copier Branching
The Copier engine uses an `adopter_shape` logic branch to render different reference architectural patterns (e.g., shape `a`, `b`, or `c` for complex meta-use guardrails). This avoids cluttering standard adoptions with advanced, unneeded patterns while retaining one unified source of truth.
