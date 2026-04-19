---
persona: maintainer
level: L2
tags: [maintainer, extend, workflow]
---

# Evolving workflow

Step-by-step procedures for larger changes: adding workspace packages, editing the template, writing specs, and smoke-testing the result.

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
7. Document the package: update the overview in `docs/adopter/build/packages.md` and add a new deep-dive page at `docs/maintainer/packages/<name>.md` (Module layout, Why, Key flows with Mermaid, Public API, Extension points, Hazards). Update `mkdocs.yml`.

## Editing the template

The Copier template is in [`template/`](https://github.com/Cognitivemesh/pyarnes/tree/main/template):

- Files with the `.jinja` suffix are rendered — remove the suffix to disable rendering.
- Jinja path segments (e.g. `template/src/{{project_module}}/`) are substituted at generation time. Use `{{project_module}}` (no spaces) to match the convention.
- Add or edit prompts in `copier.yml`. Keep every question with a sensible default so a developer can hit Enter through all of them.
- Never add `_tasks` (post-generation shell hooks) — that would force users to pass `--trust` to `copier copy`.

After editing, run the [Smoke-testing the template](#smoke-testing-the-template) workflow below. Full template-editing reference: [Editing the template](template.md).

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

## Optional graph tools

Two opt-in CLIs build token-efficient code/docs graphs for AI-assistant context. Install via the dedicated group:

```bash
uv sync --group graph
```

| Tool | PyPI | What it does |
|---|---|---|
| `code-review-graph` | `code-review-graph` | Incremental repo graph + blast-radius queries; ships an MCP server with 28 tools |
| `graphify` | `graphifyy` (double-y on PyPI) | Multimodal knowledge graph from a folder (code + docs + images) → interactive `graph.html` |

Task-runner entries (skipped silently when the group is not synced):

```bash
uv run tasks graph:blast -- packages/core/src/pyarnes_core/errors.py   # impact cone
uv run tasks graph:render                                               # writes docs/assets/graph/
```

The `--` separator forwards every argument after it to the task's underlying command, so `graph:blast` receives the file path as its positional argument.

Adopters can opt in at scaffold time via the `enable_code_graph` Copier question — that wires `code-review-graph`'s MCP server into the generated project's `.claude/mcp.json`.

## See also

- [Extension rules](rules.md) — invariants that every change must preserve.
- [Editing the template](template.md) — full template-editing reference.
- [Release workflow](../release.md) — how to cut a release once your changes land.
