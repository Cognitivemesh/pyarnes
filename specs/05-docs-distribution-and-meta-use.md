# 05 — Documentation overhaul (adopter + contributor)

## Context

Specs 01–04 change code, templates, and examples. Without a documentation update, none of that is discoverable: adopters won't know which symbols are stable, which Copier question to pick, or that Adopter C's meta-use pattern exists. Contributors won't know the semver policy or how to add a new `Guardrail` without breaking downstream pins.

The MkDocs site at `/home/user/pyarnes/docs/` already has an implicit audience split (*Getting Started / Architecture / Packages / Code Reference* for adopters, *Development* for contributors). This spec formalises that split and fills the gaps the earlier specs created.

This spec lands **after** 01–04 so every page it authors can cite real, shipped code.

## Goals / Non-goals

**Goals**

- Adopter can read `docs/getting-started/distribution.md` + `docs/template.md` and scaffold any of the three reference shapes without reading the API reference.
- Adopter C can read `docs/architecture/meta-use.md` and wire the dev-time hooks themselves.
- Contributor can read `docs/development/{evolving,extending,release,template}.md` and ship a non-breaking change confidently.
- `mkdocs.yml` nav cleanly surfaces every new page.
- `uv run tasks docs:build` clean; `uv run tasks md-lint` + `md-format` clean.

**Non-goals**

- Auto-generating API reference from docstrings (mkdocstrings). Existing `docs/api/*.md` stay as hand-written; unchanged by this spec.
- Marketing content, landing-page redesign.
- Translating docs.

## Proposed design

### New pages (adopter-facing)

| Path | Shape |
|---|---|
| `docs/getting-started/distribution.md` | The one-line recommendation ("library-first, adopter owns the CLI, `pyarnes-tasks` is dev-only"), the three-phase model (bootstrap / develop / run), and the full 25-item inventory table from the plan. This is **the** page adopters read to decide how to integrate. |
| `docs/architecture/meta-use.md` | The Adopter C pattern. Full hook code (imported from `template/.claude/hooks/` so it stays in sync), the lifecycle-per-branch pattern, `.pyarnes/` directory layout, how the bench corpus is structured. References `tests/bench/test_agent_quality.py` from Spec 04. |

### Updated pages (adopter-facing)

| Path | Update |
|---|---|
| `docs/getting-started/quickstart.md` | Replace any "run pyarnes from the CLI" framing with: pyarnes is a library; adopters build their own Typer CLI. Worked example: register a `ToolHandler`, compose a `GuardrailChain`, call `AgentLoop.run`. Link to `docs/packages/harness.md` for full API. |
| `docs/template.md` | Clarify the `uvx copier copy` flow (Spec 02). Add a worked example for each of the three adopter shapes. Document `pyarnes_ref` pinning and `uv run tasks update` (re-sync template). |
| `docs/packages/harness.md` | Add the "three-part contract" section (register tools → compose guardrails → run the loop). Document explicitly that `AgentLoop` does not auto-apply guardrails — the adopter must call `chain.check(tool, args)`. |
| `docs/packages/guardrails.md` | Add "dev-time vs runtime" section: (a) adopter wires `GuardrailChain.check` into tool dispatch at runtime; (b) Adopter C additionally wires the same chain into Claude Code pre-tool-use hooks. Include the `VerificationCompleteGuardrail` (Adopter B) and pre-tool-use hook (Adopter C) examples. |
| `docs/packages/tasks.md` | Make explicit that `pyarnes-tasks` is dev-infrastructure, **not** runtime. Full task table, the two quirks (missing paths silently dropped, pytest exit-5 treated as success), and the `[tool.pyarnes-tasks]` schema. |
| `docs/packages/bench.md` | Two worked examples: (a) adopter evaluating their shipped pipeline (precision/recall for PII; integrity rate for S3); (b) Adopter C's meta-use — scoring the coding agent with `EvalSuite` + `DiffSimilarityScorer` / `TestsPassScorer`. |
| `docs/architecture/overview.md` | Add the three-phase diagram (bootstrap / develop / run) and show where each pyarnes package enters. Emphasise: same library, two consumption patterns (shipped product vs coding-agent dev harness). |

### New pages (contributor-facing)

| Path | Shape |
|---|---|
| `docs/development/extending.md` | How contributors add new surfaces without breaking adopters: new `Guardrail` subclass, new `Scorer` subclass, new `pyarnes-tasks` task. Include the "no CLI in harness" rule from the plan's anti-patterns. |
| `docs/development/template.md` | How to evolve the Copier template without breaking existing adopters: add questions with sensible defaults, use `_migrations` for breaking changes, test with `uvx copier copy . /tmp/test-project` in CI. References `template/pyproject.toml.jinja`, `template/CLAUDE.md.jinja`, and the `.claude/hooks/` files. |
| `docs/development/release.md` | Release workflow: tag → `git push --tags` → adopters bump `pyarnes_ref` in their `pyproject.toml` → `uv sync`. Semver policy (from Spec 01). `uv run tasks update` flow. |
| `CONTRIBUTING.md` (repo root) | Short entry file: how to run `uv run tasks check`, the Red → Green → Refactor TDD loop, PR conventions, link to `docs/development/` for details. |

### Updated pages (contributor-facing)

| Path | Update |
|---|---|
| `docs/development/evolving.md` | Add "Stable API surface" section listing Spec 01's tables. Breaking-change policy. (Note: a minimal version of this section landed with Spec 01; this update expands it.) |
| `docs/development/tasks.md` | Clarify `pyarnes-tasks` is used by pyarnes itself *and* by adopters — same codebase, same CLI, different `[tool.pyarnes-tasks]` config. Document how contributors add a new task. |
| `docs/development/testing.md` | Reflect the test layout adopters inherit (`tests/unit/`, `tests/features/`, optional `tests/bench/` for Adopter C). Link to the `python-test` skill. |

### `mkdocs.yml` nav changes

```yaml
nav:
  - Home: index.md
  - Getting Started:
      - Installation: getting-started/installation.md
      - Quick Start: getting-started/quickstart.md
      - Distribution model: getting-started/distribution.md        # NEW
      - Use as template: template.md
  - Architecture:
      - Overview: architecture/overview.md
      - Error Taxonomy: architecture/errors.md
      - Lifecycle: architecture/lifecycle.md
      - Meta-use (agent-on-agent): architecture/meta-use.md        # NEW
  - Packages: { … unchanged … }
  - Code Reference: { … unchanged … }
  - Development:
      - Tasks: development/tasks.md
      - Testing: development/testing.md
      - Extending pyarnes: development/extending.md                 # NEW
      - Evolving pyarnes: development/evolving.md
      - Evolving the template: development/template.md             # NEW
      - Release workflow: development/release.md                   # NEW
```

### Content-reuse rule

Where hook code, CLI snippets, or table content already lives in Spec 01–04 artefacts (template Jinja files, reference examples), the docs page **links to them** rather than duplicating. Prevents doc drift. Use MkDocs `include-markdown` plugin if a tight inline copy is needed.

## Tests / acceptance

- `uv run tasks docs:build` exits 0 with no warnings (no broken internal links, no missing nav entries).
- `uv run tasks md-lint` + `uv run tasks md-format` clean on every new and updated file.
- Manual "cold reader" walkthrough:
  - A reader who has never seen pyarnes before opens `docs/getting-started/distribution.md`, then `docs/template.md`, then scaffolds a `pii-redaction` project end-to-end without opening the API reference.
  - A contributor opens `CONTRIBUTING.md`, then `docs/development/extending.md`, and can sketch a new `Guardrail` subclass + its docs entry without asking.
- Link-check: a CI job (`lychee` or `linkcheckmd`) passes on every doc file.
- Spot-check: every code snippet in `docs/architecture/meta-use.md` byte-matches the corresponding template file from Spec 04 (or is pulled via `include-markdown`).

## Open questions

- Do we adopt `mkdocstrings` for the `docs/api/` pages as part of this spec, or leave hand-written? Leaning: leave; tracks separately.
- Does `CONTRIBUTING.md` live at repo root (GitHub convention) or under `docs/development/`? Root, mirrored/summarised under `docs/development/`.
- Should we add a landing-page "What changed?" banner for the distribution model decision? Probably not — docs-as-source-of-truth; CHANGELOG is the announcement channel.
- Video walk-through? Out of scope here.
