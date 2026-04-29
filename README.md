# pyarnes

> A dev-time toolkit + Copier template for AI coding agents building Python applications.
> It does **not** replace Claude Code, Cursor, or Codex — it **collaborates** with them.

**pyarnes** gives your AI coding agent extra verification loops, safety enforcement, and lifecycle hooks while it writes your project. Scaffolded apps are plain Python at runtime; pyarnes lives in the dev group, wired into Claude Code hooks, an `agent_kit/` scaffolding directory, and the `tasks` CLI — not in your production wheel.

## Features (all dev-time)

- **Error taxonomy** — transient / LLM-recoverable / user-fixable / unexpected, for agent-scaffolding code under `.claude/agent_kit/`
- **Async-first conventions** — template defaults match modern tool-use patterns (asyncio, no GIL contention)
- **JSONL observability** — `.claude/hooks/` traces via `loguru`, parseable by other agents
- **Composable safety guardrails** — path, command, tool-allowlist, and AST-based semantic checks you can wrap around tool handlers in `.claude/agent_kit/`
- **Agent-quality evals** — `pyarnes-bench` framework with pluggable `Scorer`, `EvalSuite`, and JSONL result logging under `tests/bench/`
- **Lifecycle FSM helpers** — INIT → RUNNING → PAUSED → COMPLETED / FAILED with full history, available to agent-loop code you scaffold
- **Monorepo** — `pyarnes-core` + `pyarnes-harness` + `pyarnes-guardrails` + `pyarnes-bench` + `pyarnes-tasks` as independent uv workspace packages (all five are dev-tool packages — not runtime deps of scaffolded apps)
- **Cross-platform task runner** — replaces Make with `uv run tasks <name>`
- **TDD out of the box** — pytest-watch, pytest-bdd (Gherkin), pytest-sugar, hypothesis, coverage

## To use pyarnes

> Start a new python project from the pyarnes template to build. If you're building **your own project** and want to adopt pyarnes as the foundation:

```bash
uvx copier copy gh:Cognitivemesh/pyarnes my-awesome-agent
cd my-awesome-agent
uv sync                   # installs the 5 pyarnes-* packages from git URLs into [dependency-groups.dev]; your [project.dependencies] stays minimal
uv run tasks check        # lint + typecheck
```

### To build pyarnes

If you're **contributing to pyarnes** (adding a new package, editing the template, writing a feature spec):

```bash
git clone https://github.com/Cognitivemesh/pyarnes.git
cd pyarnes
uv sync                   # installs all workspace packages + dev deps
uv run tasks check        # lint + typecheck + test
uv run tasks watch        # TDD watch mode
```

See [docs/maintainer/onboard/setup.md](docs/maintainer/onboard/setup.md) for the full contributor workflow, [docs/maintainer/extend/workflow.md](docs/maintainer/extend/workflow.md) for adding packages and editing the template, and [docs/maintainer/extend/template.md](docs/maintainer/extend/template.md) for smoke-testing the result. For a practical walkthrough of how each package works internally — module layout, key flows, extension points, and the public API for each surface — see [docs/maintainer/packages/](docs/maintainer/packages/). Claude Code skills that ship with the template are documented at [docs/maintainer/extend/skills.md](docs/maintainer/extend/skills.md); adopters see [docs/adopter/build/skills.md](docs/adopter/build/skills.md). Feature specs live in [`specs/`](specs/).

## Available tasks

Inside the pyarnes, we have included a **Cross-platform task runner** which replaces **Make** with `uv run tasks <name>`

| Task | Tool Description | Task description | 
|---|---|---|
| `uv run tasks lint` | Ruff lint | This task runs a python linter checker for all the codebase |
| `uv run tasks lint:fix` | Ruff lint with auto-fix | This task runs a python linter with auto-fix for all the codebase |
| `uv run tasks format` | Ruff format | This task runs a python code formatting task.|
| `uv run tasks format:check` | Ruff check formatting task | This task runs code check formatting task.|
| `uv run tasks typecheck` | ty type checking | This task perform Type checking | 
| `uv run tasks test` | Run pytest | This task performs all the tests |
| `uv run tasks test:cov` | Run pytest with coverage | This task performs all the tests with coverage.| 
| `uv run tasks watch` | TDD watch mode (pytest-watch) | This task runs the tests if there is a change. |
| `uv run tasks security` | Bandit security scan | This task runs the security scan |
| `uv run tasks pylint` | Pylint (custom rules only) | This task runs all the custom rules only |
| `uv run tasks radon:cc` | Cyclomatic complexity (min B, filtered) | This task runs the cyclomatic complexity |
| `uv run tasks radon:mi` | Maintainability index (min B, filtered) | This task runs the maintainability index |
| `uv run tasks vulture` | Dead code detection | This task runs the dead code detection. |
| `uv run tasks complexity` | radon:cc + radon:mi | This task runs the cyclomatic complexity and maintainability index |
| `uv run tasks md-lint` | Markdown lint | This task runs the markdown linter checks |
| `uv run tasks md-format` | Markdown format | This task runs the markdown format checks |
| `uv run tasks yaml-lint` | YAML lint | This task runs the YAML linter checks |
| `uv run tasks docs` | Generate docstrings (doq) | This task generates document strings |
| `uv run tasks docs:serve` | Serve MkDocs locally | This task serves the mkdocs |
| `uv run tasks docs:build` | Build MkDocs site | This task serves the mkdocs site after build it |
| `uv run tasks check` | lint + typecheck + test | This task do the checks |
| `uv run tasks ci` | Full CI pipeline | This task runst the complete CI pipeline |

## Deterministic Tools Framework 

### Error Taxonomy 

This taxonomy applies when writing agent scaffolding (e.g. under
`.claude/agent_kit/` in scaffolded projects). It is not imposed on the
runtime code in `src/`.

```text
┌─────────────────┐    retry (max 2)     ┌─────────────────┐
│ TransientError  │ ────────────────────│ Tool re-executed │
└─────────────────┘                      └─────────────────┘

┌─────────────────────┐  ToolMessage     ┌─────────────────┐
│ LLMRecoverableError │ ───────────────► │ Model adjusts   │
└─────────────────────┘  (is_error=True) └─────────────────┘

┌─────────────────┐  interrupt           ┌─────────────────┐
│ UserFixableError│ ──────────────────►  │ Human input     │
└─────────────────┘                      └─────────────────┘

┌─────────────────┐  bubble up           ┌───────────────────┐
│ UnexpectedError │ ──────────────────►  │ Debug / postmortem│
└─────────────────┘                      └───────────────────┘
```

## Monorepo structure

The project is **Monorepo** — `pyarnes-core` + `pyarnes-harness` + `pyarnes-guardrails` + `pyarnes-bench` + `pyarnes-tasks` as independent uv workspace packages

```text
pyarnes/
├── pyproject.toml              # Root workspace: dev deps + shared tool config
├── copier.yml                  # Prompts for `uvx copier copy gh:Cognitivemesh/pyarnes`
├── mkdocs.yml                  # MkDocs Material documentation site
├── packages/
│   ├── core/                   # pyarnes-core (types, errors, lifecycle, logging)
│   │   ├── pyproject.toml
│   │   └── src/pyarnes_core/
│   ├── harness/                # pyarnes-harness (loop, tools, capture)
│   │   ├── pyproject.toml
│   │   └── src/pyarnes_harness/
│   ├── guardrails/             # pyarnes-guardrails (composable safety guardrails)
│   │   ├── pyproject.toml
│   │   └── src/pyarnes_guardrails/
│   ├── bench/                  # pyarnes-bench (evaluation & benchmarking)
│   │   ├── pyproject.toml
│   │   └── src/pyarnes_bench/
│   └── tasks/                  # pyarnes-tasks (cross-platform task runner)
│       ├── pyproject.toml
│       └── src/pyarnes_tasks/
├── template/                   # Copier template — rendered into new projects
├── docs/                       # MkDocs documentation source
└── tests/
    ├── unit/
    └── features/               # BDD / Gherkin feature files
```

## pyarnes Tooling stack

| Category | Tool | Purpose |
|---|---|---|
| Package manager | [uv](https://github.com/astral-sh/uv) | Fast dependency management + workspace |
| Linting & formatting | [Ruff](https://docs.astral.sh/ruff/) | Blazing-fast linter + formatter |
| Type checking | [ty](https://github.com/astral-sh/ty) | Fast type checker (Astral) |
| Security | [Bandit](https://bandit.readthedocs.io/) | Security linter |
| Complexity | [Radon](https://radon.readthedocs.io/) | Cyclomatic complexity + maintainability |
| Dead code | [Vulture](https://github.com/jendrikseipp/vulture) | Unused code detection |
| Profiling | [pyinstrument](https://github.com/joerick/pyinstrument) | Statistical profiler |
| Testing | [pytest](https://docs.pytest.org/) | Test framework |
| BDD | [pytest-bdd](https://pytest-bdd.readthedocs.io/) | Gherkin feature files |
| Property testing | [Hypothesis](https://hypothesis.readthedocs.io/) | Property-based testing |
| Coverage | [pytest-cov](https://pytest-cov.readthedocs.io/) | Coverage reporting |
| Test UX | [pytest-sugar](https://github.com/Teemu/pytest-sugar) | Pretty test output |
| TDD watcher | [pytest-watch](https://github.com/joeyespo/pytest-watch) | Auto-rerun on file changes |
| Documentation | [MkDocs Material](https://squidfunk.github.io/mkdocs-material/) | Documentation site |
| Logging | [loguru](https://loguru.readthedocs.io/) | JSONL structured logging |
| Functional | [returns](https://returns.readthedocs.io/) / [toolz](https://toolz.readthedocs.io/) / [funcy](https://funcy.readthedocs.io/) / [more-itertools](https://more-itertools.readthedocs.io/) | Railway-oriented errors, data pipelines, collection helpers, advanced iterables — see `CLAUDE.md` for usage guidance |

## License

MIT
