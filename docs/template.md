# Use pyarnes as a template

`pyarnes` is both a working monorepo **and** a Copier template. Any developer can bootstrap a new agentic-harness project that depends on the pyarnes packages — no copy-paste, no PyPI account required.

## Bootstrap — one command

```bash
uvx copier copy gh:Cognitivemesh/pyarnes my-awesome-agent
```

`uvx` avoids any extra install. Copier then prompts for a handful of answers — every question has a default, so a developer can hit Enter through all of them:

| Prompt | Default | What it's used for |
|---|---|---|
| `project_name` | destination directory name | `pyproject.toml` name, docs title |
| `project_description` | `"A pyarnes-based project"` | one-line description in pyproject + README |
| `python_version` | `3.13` | `requires-python`, `.python-version` |
| `pyarnes_ref` | `main` | git ref that the five pyarnes deps pin to |

**No author name or email is asked.** The generated `pyproject.toml` omits the `authors` field — PEP 621 allows that, and developers can add it later.

Then:

```bash
cd my-awesome-agent
uv sync                  # resolves 5 pyarnes-* packages from git URLs
uv run tasks check       # lint + typecheck (test is a no-op until you add tests)
git init && git add . && git commit -m "Initial commit"
```

## What you get

```
my-awesome-agent/
├── pyproject.toml                # 5 pyarnes-* deps pinned via git URL
├── README.md                     # starter project README
├── CLAUDE.md                     # conventions + harness cheatsheet
├── LICENSE                       # MIT
├── mkdocs.yml                    # docs site configuration
├── .python-version               # pinned Python version
├── .gitignore .markdownlint.yaml .yamllint.yaml
├── .claude/
│   └── skills/
│       └── python-test/
│           └── SKILL.md          # scaffolds tests/ on demand
├── docs/
│   ├── index.md
│   ├── getting-started/{installation,quickstart}.md
│   └── development/tasks.md
└── src/
    └── my_awesome_agent/
        └── __init__.py           # your module entrypoint
```

**What you do _not_ get:**

- `packages/` — the five pyarnes-* packages are installed as git-URL dependencies, never copied.
- `tests/` — the project starts empty. Ask Claude Code "write a test for X" and the bundled **python-test skill** creates `tests/unit/` + your first test file, following pyarnes TDD conventions.

## The five pyarnes dependencies

Each one is pinned in `pyproject.toml` as:

```toml
"pyarnes-core       @ git+https://github.com/Cognitivemesh/pyarnes.git@{pyarnes_ref}#subdirectory=packages/core",
"pyarnes-harness    @ git+https://github.com/Cognitivemesh/pyarnes.git@{pyarnes_ref}#subdirectory=packages/harness",
"pyarnes-guardrails @ git+https://github.com/Cognitivemesh/pyarnes.git@{pyarnes_ref}#subdirectory=packages/guardrails",
"pyarnes-bench      @ git+https://github.com/Cognitivemesh/pyarnes.git@{pyarnes_ref}#subdirectory=packages/bench",
"pyarnes-tasks      @ git+https://github.com/Cognitivemesh/pyarnes.git@{pyarnes_ref}#subdirectory=packages/tasks",
```

`uv sync` clones the pyarnes repo once, extracts each `#subdirectory=…` slice, and caches the result. Subsequent syncs are offline.

## Pulling in template updates

The pyarnes template evolves over time — new tooling, updated conventions, improved skill files. To fold those improvements into an existing project:

```bash
uv run tasks update
```

This wraps `uvx copier update` — you don't need to know Copier's flags. Merge conflicts (if any) are surfaced interactively; review, resolve, commit.

`uv run tasks update` works only when the generated project contains a `.copier-answers.yml` file. Copier writes this file automatically the first time you bootstrap from a real git ref (`gh:Cognitivemesh/pyarnes`).

## Pinning a specific pyarnes version

For reproducibility, answer the `pyarnes_ref` prompt with a git tag (e.g., `v0.2.0`) when you bootstrap. All five pyarnes-* git URLs will resolve against that tag and `uv.lock` will pin the exact commit.

## What's under the hood

The template lives in [`template/`](https://github.com/Cognitivemesh/pyarnes/tree/main/template) inside the pyarnes repo. The [`copier.yml`](https://github.com/Cognitivemesh/pyarnes/blob/main/copier.yml) at the repo root declares the four prompts + computed `project_module` / `current_year` values.

- Path-level Jinja (e.g. `template/src/{{project_module}}/`) gives each generated project its own Python module directory named after the chosen project.
- File contents with a `.jinja` suffix are rendered; others are copied verbatim (dotfiles, config files).
- No post-generation shell hooks — the template is pure Jinja, so `uvx copier copy …` never requires `--trust`.

See the [architecture overview](architecture/overview.md) for where the template lives inside the pyarnes monorepo.
