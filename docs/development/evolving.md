# Evolving pyarnes

This page is for contributors and maintainers of **pyarnes itself** — people working on the five `pyarnes-*` packages and the template shipped inside this repo. If you just want to use pyarnes as a starting point for your own project, see [Use as template](../template.md) instead.

## Repository layout

```text
pyarnes/
├── copier.yml                  # Template prompts (project_name, …, pyarnes_ref)
├── template/                   # Copier template tree rendered into new projects
│   ├── pyproject.toml.jinja    # 5 git-URL deps, no workspace config
│   ├── src/{{project_module}}/__init__.py.jinja
│   ├── CLAUDE.md.jinja  README.md.jinja  LICENSE.jinja  mkdocs.yml.jinja
│   ├── .claude/skills/python-test/SKILL.md
│   └── docs/…
├── packages/                   # uv-workspace packages (the dependencies)
│   ├── core/         → pyarnes-core       (types, errors, lifecycle, logging)
│   ├── harness/      → pyarnes-harness    (loop, tools, capture)
│   ├── guardrails/   → pyarnes-guardrails (safety checks)
│   ├── bench/        → pyarnes-bench      (evaluation framework)
│   └── tasks/        → pyarnes-tasks      (cross-platform task runner)
├── tests/                      # Unit + BDD/Gherkin tests for the packages
├── docs/                       # MkDocs Material documentation source
├── specs/                      # Feature specifications (monorepo-internal, excluded from template)
└── pyproject.toml              # Root workspace (no buildable wheel, dev deps only)
```

Each workspace package has its own `pyproject.toml`. The root `pyproject.toml` declares the uv workspace, the shared tool configuration (ruff, ty, pytest, bandit, coverage, pylint, pymarkdown, yamllint), and the `[tool.pyarnes-tasks]` block that drives the `tasks` CLI.

## Daily workflow

```bash
uv sync                   # install all workspace packages + dev deps
uv run tasks help         # list available tasks
uv run tasks watch        # TDD watch mode (pytest-watch)
uv run tasks check        # lint + typecheck + test
uv run tasks ci           # format:check + lint + typecheck + test:cov + security
```

The TDD discipline is Red → Green → Refactor — see [`.claude/commands/tdd.md`](https://github.com/Cognitivemesh/pyarnes/blob/main/.claude/commands/tdd.md) for the exact cycle.

## Making a change inside a package

1. Work inside `packages/<pkg>/src/pyarnes_<pkg>/`.
2. Write the failing test in `tests/unit/test_<module>.py` or `tests/features/<feature>.feature`.
3. Run `uv run tasks watch` in another terminal to see it turn red → green.
4. Run `uv run tasks check` before committing.

## Adding a new workspace package

1. Create `packages/<name>/` with:
   - `pyproject.toml` using the same pattern as `packages/tasks/pyproject.toml` (hatchling build, `[project.scripts]` if it exposes a CLI).
   - `src/pyarnes_<name>/__init__.py` (+ `py.typed` for typed-package marking).
   - A short `README.md`.
2. The root `[tool.uv.workspace] members = ["packages/*"]` picks it up automatically.
3. Add it to root `[tool.uv.sources]` as `pyarnes-<name> = { workspace = true }`.
4. Add it to root `dependencies` if the monorepo itself should install it.
5. Update `template/pyproject.toml.jinja` if generated projects should depend on it — add a new git-URL line:
   ```toml
   "pyarnes-<name> @ git+https://github.com/Cognitivemesh/pyarnes.git@{{ pyarnes_ref }}#subdirectory=packages/<name>",
   ```
6. Add the package to the `[tool.ruff] src`, `[tool.coverage.run] source`, and `[tool.ruff.lint.isort] known-first-party` lists in the root `pyproject.toml`.
7. Document the package in `docs/packages/<name>.md` and add it to `mkdocs.yml`.

## Editing the template

The Copier template is in [`template/`](https://github.com/Cognitivemesh/pyarnes/tree/main/template):

- Files with the `.jinja` suffix are rendered — remove the suffix to disable rendering.
- Jinja path segments (e.g. `template/src/{{project_module}}/`) are substituted at generation time. Use `{{project_module}}` (no spaces) to match the convention.
- Add or edit prompts in `copier.yml`. Keep every question with a sensible default so a developer can hit Enter through all of them.
- Never add `_tasks` (post-generation shell hooks) — that would force users to pass `--trust` to `copier copy`.

After editing, run the [Smoke-testing the template](#smoke-testing-the-template) workflow below.

## Writing a feature spec

Non-trivial work starts with a short spec in [`specs/`](https://github.com/Cognitivemesh/pyarnes/tree/main/specs). Use one Markdown file per feature; see `specs/README.md` for the minimum shape (context, goals/non-goals, design, tests, open questions). The `specs/` folder lives only in the monorepo — it's excluded from the Copier template so adopters never see it.

## Smoke-testing the template

Because Copier only writes `.copier-answers.yml` (needed for `copier update`) when the source repo is at a clean git ref, testing the template against uncommitted changes skips that file. Workflow:

```bash
# Local structure-only check (works against uncommitted changes):
rm -rf /tmp/pyarnes-smoke
uvx copier copy --defaults \
  --data project_name=smoke-test \
  --data project_description=demo \
  "$(pwd)" /tmp/pyarnes-smoke
find /tmp/pyarnes-smoke -type f | sort   # inspect the generated tree

# Full end-to-end (requires pushed commits so the git URL resolves):
git push origin main
uvx copier copy gh:Cognitivemesh/pyarnes /tmp/pyarnes-e2e
cd /tmp/pyarnes-e2e
uv sync                        # pulls all 5 pyarnes-* packages from git URLs
uv run tasks check             # lint + typecheck (test is a no-op)
uvx copier update              # round-trip — should apply cleanly with no conflicts
```

The `scripts/smoke-template.sh` helper automates the structural portion and is invoked before tagging a release.

## Releasing a pinned template version

When you want generated projects to be able to pin to a stable version:

1. Make your changes on `main`, push, and ensure tests are green.
2. Tag: `git tag v0.X.0 && git push --tags`.
3. Announce the tag — developers can now bootstrap with:
   ```bash
   uvx copier copy gh:Cognitivemesh/pyarnes my-app
   # answer pyarnes_ref with "v0.X.0"
   ```
4. Existing projects can upgrade with:
   ```bash
   uv run tasks update       # copier update against the new ref
   ```

No PyPI publishing is involved — the entire distribution story rides on git URLs.

## Known constraints

- Python 3.13+ only. The template pins `>=3.13` and pyarnes's own code uses 3.13 features (match statements, frozen slotted dataclasses).
- uv required. All workflows are expressed as `uv run tasks …`; no Make, no shell scripts beyond `scripts/`.
- Generated projects cannot use pyarnes offline on first sync — the git URLs need one-time clone access. uv caches the result for subsequent installs.
