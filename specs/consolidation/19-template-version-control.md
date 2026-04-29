# pyarnes_swarm — Template Version Control

> **Spec header**
>
> | Field | Value |
> |---|---|
> | **Title** | pyarnes_swarm — Template Version Control |
> | **Status** | active |
> | **Type** | governance |
> | **Tags** | template, version, copier |
> | **Owns** | Copier template evolution policy, adopter migration rules, copier.yml versioning, template-level breaking-change handling |
> | **Depends on** | 10-hook-integration.md, 18-api-surface-governance.md |
> | **Extends** | — |
> | **Supersedes** | — |
> | **Read after** | 18-api-surface-governance.md |
> | **Read before** | — |
> | **Not owned here** | external hook contract (see `10-hook-integration.md`); api-surface stability (see `18-api-surface-governance.md`); package structure (see `01-package-structure.md`) |
> | **Last reviewed** | 2026-04-29 |

## Design Rationale

The pyarnes framework relies on Copier for scaffolding new adoptions. Managing updatability and structure shapes across adoptions is critical.

## Specification

### Template Version Control

#### `_migrations` Placeholder
To handle evolutionary updates when adopters run `copier update`, the template includes a `_migrations` system. By tracking structure changes in a robust migration path, adopters can seamlessly evolve their projects without destructive diff overwrites on business logic.

#### `adopter_shape` Copier Branching
The Copier engine uses an `adopter_shape` logic branch to render different reference architectural patterns (e.g., shape `a`, `b`, or `c` for complex meta-use guardrails). This avoids cluttering standard adoptions with advanced, unneeded patterns while retaining one unified source of truth.

## Appendix

### Notes

> See also `10-hook-integration.md` § Adopter shapes (Copier template) — full adopter shapes and dev-time hook details.
