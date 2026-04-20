# Contributing to pyarnes

Short version: work on a branch, run `uv run tasks check`, open a PR.

## Setup

```bash
git clone https://github.com/Cognitivemesh/pyarnes
cd pyarnes
uv sync
uv run tasks help
```

## Daily workflow

```bash
uv run tasks watch        # TDD — pytest-watch
uv run tasks check        # lint + typecheck + test (use before pushing)
uv run tasks ci           # full gate — format:check + lint + typecheck + test:cov + security
```

The TDD discipline is **Red → Green → Refactor**.

## What goes where

- `packages/core|harness|guardrails|bench|tasks/` — the five runtime
  packages. Contracts are stable; see
  [`CHANGELOG.md`](CHANGELOG.md) for the public-surface tables.
- `template/` + `copier.yml` — the Copier template adopters use to
  scaffold their projects. See
  [`docs/maintainer/extend/template.md`](docs/maintainer/extend/template.md).
- `tests/unit/` — unit tests. `tests/features/` — Gherkin/pytest-bdd.
  `tests/template/` — Copier template smoke tests.
- `specs/` — feature specifications. Non-trivial work starts with a spec
  under `specs/NN-<area>-<title>.md` so reviewers see design before code.

## PR conventions

- One logical change per PR. Keep diffs reviewable.
- Commit messages follow Conventional Commits style (`feat(core): …`,
  `fix(harness): …`, `docs: …`).
- Every new public symbol shipped in a PR must:
  - Be exported from the package's `__init__.py` `__all__`.
  - Be listed in `CHANGELOG.md` under `## [Unreleased]`.
  - Be added to `STABLE_SURFACE` in
    `tests/unit/test_stable_surface.py`.
  - Have at least one test.

## Links

- Full contributor docs: [`docs/maintainer/`](docs/maintainer/)
- Stable surface and semver policy: [`CHANGELOG.md`](CHANGELOG.md)
- Release workflow: [`docs/maintainer/release.md`](docs/maintainer/release.md)
- Extending the library without breaking adopters: [`docs/maintainer/extend/rules.md`](docs/maintainer/extend/rules.md)
- Evolving the Copier template: [`docs/maintainer/extend/template.md`](docs/maintainer/extend/template.md)

## Reporting issues

Open a GitHub issue with a minimal reproducer and the output of
`uv run tasks check`. For security concerns, email the maintainers listed
in `pyproject.toml` rather than opening a public issue.
