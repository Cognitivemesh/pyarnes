# pyarnes_swarm — Tooling Artifacts and Repo Hygiene

> **Spec header**
>
> | Field | Value |
> |---|---|
> | **Title** | pyarnes_swarm — Tooling Artifacts and Repo Hygiene |
> | **Status** | active |
> | **Type** | testing |
> | **Tags** | tooling, artifacts, devex |
> | **Owns** | managed tooling artifacts policy, repository hygiene (.gitignore rules), template scaffolding exclusions in copier.yml, development task degradation |
> | **Depends on** | 01-package-structure.md |
> | **Extends** | 19-template-version-control.md |
> | **Supersedes** | — |
> | **Read after** | 03-test-map.md |
> | **Read before** | 18-api-surface-governance.md |
> | **Not owned here** | package structure / layer rules (see `01-package-structure.md`); template versioning (see `19-template-version-control.md`); semver policy (see `18-api-surface-governance.md`) |
> | **Last reviewed** | 2026-04-29 |

## Design Rationale

As `pyarnes` consolidates into the single `pyarnes_swarm` package, the repository root will continue to host artifacts from opt-in and external developer tools. These artifacts must not pollute the shipped package, the test environment, or the scaffolded adopter projects.

This specification outlines the handling of in-tree developer artifacts produced by `pyarnes_bench.audit` and other dev-time tools.

## Specification

### Managed Tooling Artifacts

The following directories and files are considered transient developer artifacts:
- `.pyarnes/` — Internal tool-call JSONL logs, violation trails, and the audit graph (`.pyarnes/audit/graph.json`) produced by `pyarnes_bench.audit`.
- `.claude/` — Claude Code sessions, prompts, and run logs.
- `tests/bench/out/` — Output logs from evaluator or scoring runs.

### Repository Hygiene (Git and Linting)

All transient artifacts must be strictly ignored by version control and static analysis tools.

- **`.gitignore`**: Must actively ignore `.pyarnes/` and `.claude/`.
- **`pyproject.toml`**: `ruff`, `bandit`, `pytest`, `vulture`, and `radon` configurations must explicitly exclude these directories to prevent parsing errors or false-positive security warnings on generated JSON.

### Template Scaffolding Exclusions (`copier.yml`)

The `copier.yml` blueprint must explicitly exclude developer artifacts so they do not bleed into adopter workspaces during `uvx copier copy`.

- `_exclude` must include `.pyarnes/**` and `.pyarnes`.
- `_exclude` must include `.claude/**` (except for the intentionally scaffolded `agent_kit` and `hooks` when `enable_dev_hooks` is true).

### Development Tasks (`pyarnes-tasks`)

The `tasks` configuration in `pyproject.toml` defines four `audit:*` developer tasks (`audit:build`, `audit:show`, `audit:analyze`, `audit:check`) that drive `pyarnes_bench.audit`. They are in-tree Python modules — no opt-in install or graceful-degradation path is required, because the implementation lives in the same workspace.
