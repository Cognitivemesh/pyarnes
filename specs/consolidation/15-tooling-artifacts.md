# External Tooling and Workflow Artifacts

> **Spec header**
>
> | Field | Value |
> |---|---|
> | **Title** | pyarnes_swarm — Tooling Artifacts and Repo Hygiene |
> | **Status** | active |
> | **Type** | testing |
> | **Owns** | managed tooling artifacts policy, repository hygiene (.gitignore rules), template scaffolding exclusions in copier.yml, development task degradation |
> | **Depends on** | 01-package-structure.md |
> | **Extends** | 17-template-version-control.md |
> | **Supersedes** | — |
> | **Read after** | 09-test-map.md |
> | **Read before** | 16-api-surface-governance.md |
> | **Not owned here** | package structure / layer rules (see `01-package-structure.md`); template versioning (see `17-template-version-control.md`); semver policy (see `16-api-surface-governance.md`) |
> | **Last reviewed** | 2026-04-29 |

As `pyarnes` consolidates into the single `pyarnes_swarm` package, the repository root will continue to host artifacts from opt-in and external developer tools. These artifacts must not pollute the shipped package, the test environment, or the scaffolded adopter projects.

This specification outlines the handling of external tooling artifacts, specifically focusing on the deferred `code-review-graph` integration and benchmark logs.

## Managed Tooling Artifacts

The following directories and files are considered transient developer artifacts:
- `.code-review-graph/` — Generated graph databases and HTML reports (`graph.html`).
- `.claude/` — Claude Code sessions, prompts, and run logs.
- `.pyarnes/` — Internal tool call jsonl logs and violation trails.
- `tests/bench/out/` — Output logs from evaluator or scoring runs.

## Repository Hygiene (Git and Linting)

All transient artifacts must be strictly ignored by version control and static analysis tools.

- **`.gitignore`**: Must actively ignore `.code-review-graph/`, `.claude/`, and `.pyarnes/`.
- **`pyproject.toml`**: `ruff`, `bandit`, `pytest`, `vulture`, and `radon` configurations must explicitly exclude these directories to prevent parsing errors or false-positive security warnings on generated HTML/JSON.

## Template Scaffolding Exclusions (`copier.yml`)

The `copier.yml` blueprint must explicitly exclude developer artifacts so they do not bleed into adopter workspaces during `uvx copier copy`.

- `_exclude` must include `.code-review-graph/**` and `.code-review-graph`.
- `_exclude` must include `.claude/**` (except for the intentionally scaffolded `agent_kit` and `hooks` when `enable_dev_hooks` is true).

## Development Tasks (`pyarnes-tasks` migration)

While `pyarnes-tasks` is being refactored out of the runtime path, developer workflow tasks (`graph:render`, `graph:blast`) remain relevant for mono-repo development.
- The `tasks` configuration in `pyproject.toml` should define these as pure developer aliases.
- These commands must gracefully degrade if `graphify` or `code-review-graph` are not installed locally. The test suite must mock these to verify graceful failure without requiring the binaries in the CI environment.
