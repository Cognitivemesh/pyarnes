# pyarnes

> A minimal agentic harness engineering template for Python.
> It does **not** replace Claude Code, Cursor, or Codex — it **collaborates** with them.

**pyarnes** adds verification loops, safety enforcement, and lifecycle management that AI coding tools miss. It captures raw outputs and errors, feeds that reality back to the model, applies guardrails around what the system can touch, and makes every step visible and debuggable.

## Features

- **Four error types** — transient (retry with backoff), LLM-recoverable (return as ToolMessage), user-fixable (interrupt for human input), and unexpected (bubble up for debugging)
- **Async-first** — built on `asyncio` to maximise performance and avoid GIL contention
- **JSONL observability** — single logging layer via `loguru` that agents can parse
- **Safety guardrails** — composable path, command, and tool-allowlist checks
- **Lifecycle FSM** — INIT → RUNNING → PAUSED → COMPLETED / FAILED with full history
- **Monorepo** — `pyarnes-core` + `pyarnes-harness` + `pyarnes-guardrails` + `pyarnes-bench` + `pyarnes-tasks` as independent uv workspace packages
- **Cross-platform task runner** — replaces Make with `uv run tasks <name>`
- **TDD out of the box** — pytest-watch, pytest-bdd (Gherkin), pytest-sugar, hypothesis, coverage

## Two ways to use pyarnes

### A. Start a new agentic-harness project from the pyarnes template

If you're building **your own project** and want to adopt pyarnes as the foundation:

```bash
uvx copier copy gh:Cognitivemesh/pyarnes my-awesome-agent
cd my-awesome-agent
uv sync                   # pulls the 5 pyarnes-* packages from git URLs
uv run tasks check        # lint + typecheck
```

No PyPI publishing, no copied source — your project **depends on** the pyarnes packages via git URL. Later, `uv run tasks update` pulls template improvements into your project (wraps `copier update` under the hood).

Full walkthrough: [docs/adopter/bootstrap/scaffold.md](docs/adopter/bootstrap/scaffold.md).

### B. Work on pyarnes itself

If you're **contributing to pyarnes** (adding a new package, editing the template, writing a feature spec):

```bash
git clone https://github.com/Cognitivemesh/pyarnes.git
cd pyarnes
uv sync                   # installs all 5 workspace packages + dev deps
uv run tasks check        # lint + typecheck + test
uv run tasks watch        # TDD watch mode
```

See [docs/maintainer/onboard/setup.md](docs/maintainer/onboard/setup.md) for the full contributor workflow, [docs/maintainer/extend/workflow.md](docs/maintainer/extend/workflow.md) for adding packages and editing the template, and [docs/maintainer/extend/template.md](docs/maintainer/extend/template.md) for smoke-testing the result. For a practical walkthrough of how each package works internally — module layout, key flows, extension points, and the public API for each surface — see [docs/maintainer/packages/](docs/maintainer/packages/). Claude Code skills that ship with the template are documented at [docs/maintainer/extend/skills.md](docs/maintainer/extend/skills.md); adopters see [docs/adopter/build/skills.md](docs/adopter/build/skills.md). Feature specs live in [`specs/`](specs/).

## Available tasks

| Task | Description |
|---|---|
| `uv run tasks lint` | Ruff lint |
| `uv run tasks lint:fix` | Ruff lint with auto-fix |
| `uv run tasks format` | Ruff format |
| `uv run tasks format:check` | Check formatting |
| `uv run tasks typecheck` | ty type checking |
| `uv run tasks test` | Run pytest |
| `uv run tasks test:cov` | Run pytest with coverage |
| `uv run tasks watch` | TDD watch mode (pytest-watch) |
| `uv run tasks security` | Bandit security scan |
| `uv run tasks pylint` | Pylint (custom rules only) |
| `uv run tasks radon:cc` | Cyclomatic complexity (min B, filtered) |
| `uv run tasks radon:mi` | Maintainability index (min B, filtered) |
| `uv run tasks vulture` | Dead code detection |
| `uv run tasks complexity` | radon:cc + radon:mi |
| `uv run tasks md-lint` | Markdown lint |
| `uv run tasks md-format` | Markdown format |
| `uv run tasks yaml-lint` | YAML lint |
| `uv run tasks docs` | Generate docstrings (doq) |
| `uv run tasks docs:serve` | Serve MkDocs locally |
| `uv run tasks docs:build` | Build MkDocs site |
| `uv run tasks check` | lint + typecheck + test |
| `uv run tasks ci` | Full CI pipeline |

## Error taxonomy

```text
┌─────────────────┐    retry (max 2)     ┌─────────────────┐
│ TransientError   │ ──────────────────── │ Tool re-executed │
└─────────────────┘                      └─────────────────┘

┌─────────────────────┐  ToolMessage     ┌─────────────────┐
│ LLMRecoverableError │ ───────────────► │ Model adjusts    │
└─────────────────────┘  (is_error=True) └─────────────────┘

┌─────────────────┐  interrupt           ┌─────────────────┐
│ UserFixableError │ ──────────────────► │ Human input      │
└─────────────────┘                      └─────────────────┘

┌─────────────────┐  bubble up           ┌─────────────────┐
│ UnexpectedError  │ ──────────────────► │ Debug / postmortem│
└─────────────────┘                      └─────────────────┘
```

## Monorepo structure

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

## Tooling stack

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
