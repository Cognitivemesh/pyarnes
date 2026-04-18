# 02 — Copier template for adopter scaffolding

## Context

The plan's distribution recommendation is **library-first, adopter owns the CLI, `pyarnes-tasks` is dev-only**. For this to work in practice, `uvx copier copy gh:Cognitivemesh/pyarnes <dest>` must produce a project that already pulls pyarnes packages as git deps (pinned to `pyarnes_ref`), already has `[tool.pyarnes-tasks]` configured, and already contains a starter `pipeline.py` + `cli.py` that demonstrate the three-part contract (register tools → compose guardrails → run the loop).

Today `template/` exists but does not yet branch on adopter shape. The three reference adopters (A: PII, B: S3, C: RTM+Toggl) share 80% of the scaffold; the remaining 20% — project-specific `ToolHandler`s and `Guardrail`s — is what Copier should stamp based on a single question.

This spec does not ship Adopter C's dev-time hooks. Those are orthogonal and land in Spec 04.

## Goals / Non-goals

**Goals**

- Adopter runs one command and gets a working `uv run <their-cli> --help`.
- Template covers all three reference shapes plus a `blank` fallback.
- `[tool.pyarnes-tasks]` pre-wired so `uv run tasks check` works from minute one.
- `CLAUDE.md.jinja` tailored to the adopter's shape so coding agents pick up the right conventions.

**Non-goals**

- Runtime behaviour of the shipped packages (Spec 01).
- Dev-time hooks / agent-quality bench (Spec 04).
- Docs overhaul beyond what the template itself ships (Spec 05).
- Full-fidelity reference implementations — only starter stubs here; complete examples land in Spec 03 under `packages/examples/`.

## Proposed design

### Copier question

Add to `copier.yml`:

```yaml
adopter_shape:
  type: str
  help: Which reference shape best fits this project?
  choices:
    - pii-redaction
    - s3-sweep
    - rtm-toggl-agile
    - blank
  default: blank

pyarnes_ref:
  type: str
  help: Git ref of pyarnes to pin (tag, branch, or commit SHA).
  default: main
```

### Template files (Jinja)

- `template/pyproject.toml.jinja` — pins `pyarnes-core`, `pyarnes-harness`, `pyarnes-guardrails`, `pyarnes-bench`, `pyarnes-tasks` via `git+https://github.com/Cognitivemesh/pyarnes.git@{{ pyarnes_ref }}#subdirectory=packages/<pkg>`. Appends shape-specific runtime deps under a `{% if adopter_shape == "..." %}` block (A: `kreuzberg`, `presidio-analyzer`, `presidio-anonymizer==2.2.354`, `spacy`, `scikit-learn`, `typer`; B: `boto3`, `aioboto3`, `typer`, `xxhash`; C: `httpx`, `pydantic`, `typer`).
- `template/src/{{ project_slug }}/pipeline.py.jinja` — `async def run_pipeline(...)` that builds `ToolRegistry`, `GuardrailChain`, `AgentLoop`, awaits `.run(messages)`. Starter body branches on `adopter_shape`.
- `template/src/{{ project_slug }}/cli.py.jinja` — Typer app with shape-appropriate subcommands (A: `ingest`/`redact`; B: `download`/`verify`/`sweep`; C: `sync-rtm`/`sync-toggl`/`promote`; blank: `run`). Registered as `[project.scripts]`.
- `template/src/{{ project_slug }}/tools/__init__.py.jinja` + one stub file per shape showing a minimal `ToolHandler` subclass.
- `template/src/{{ project_slug }}/guardrails.py.jinja` — one custom `Guardrail` per shape (A: `PIIGuardrail` stub; B: `VerificationCompleteGuardrail` stub; C: `ApiQuotaGuardrail` stub).
- `template/CLAUDE.md.jinja` — shape-specific quick commands + conventions; references the `python-test` skill.
- `template/.claude/skills/python-test/SKILL.md.jinja` — ships with the project; contributors keep it in sync.
- `template/pyproject.toml.jinja` includes `[tool.pyarnes-tasks]` block with sensible defaults (paths, coverage targets, pytest args).

### Copier behaviour

- `copier.yml` `_exclude` keeps `specs/`, `docs/`, `packages/` out of the copy (already the case; verify).
- `_skip_if_exists` for `CLAUDE.md` so re-running `uv run tasks update` preserves adopter edits.
- Add `_migrations` placeholder (empty list) so future breaking template changes have a hook.

### Files touched

- `copier.yml` — add `adopter_shape`, `pyarnes_ref`, any new excludes.
- `template/pyproject.toml.jinja` — shape-branched deps + `[tool.pyarnes-tasks]`.
- `template/src/{{ project_slug }}/{pipeline,cli}.py.jinja` — new.
- `template/src/{{ project_slug }}/tools/` + `guardrails.py.jinja` — new, shape-branched.
- `template/CLAUDE.md.jinja` — shape-branched.
- `template/.claude/skills/python-test/SKILL.md.jinja` — new or updated.

## Tests / acceptance

- `tests/template/test_scaffold_pii.py` — runs `uvx copier copy . /tmp/t-pii --data adopter_shape=pii-redaction --defaults`, then `uv sync`, then `uv run <slug> --help` exits 0.
- Parallel tests for `s3-sweep`, `rtm-toggl-agile`, `blank`.
- `tests/template/test_tasks_config.py` — after scaffold, `uv run tasks check` on the empty project exits 0 (no tests, no sources → still passes; pytest exit-5 treated as success).
- `uvx copier copy . /tmp/t` with no `pyarnes_ref` defaults to `main` and produces a resolvable `pyproject.toml`.
- Manual: open `/tmp/t-*/CLAUDE.md` and verify the quick commands section matches the chosen shape.

## Open questions

- Do we ship a `uv.lock` from the template, or let adopters generate their own? Leaning: no lockfile shipped; adopters generate on first `uv sync`.
- Should `pyarnes_ref` default to `main` (bleeding edge) or the latest tag (stable)? Defer until Spec 01 lands the first tag.
- Is a fifth shape worth pre-shipping (HTTP webhook consumer? LLM-as-judge evaluator?) or does `blank` cover the long tail? Defer.

Next: `03-examples-adopter-a-and-b.md`
