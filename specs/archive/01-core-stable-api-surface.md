# 01 — Core stable API surface

**Status:** Implemented — stable surface enforced via
`tests/unit/test_stable_surface.py`. Last refreshed 2026-04-22 to cover
the Phase 1–4 additions (`Budget`, `SecretLeakGuardrail`,
`NetworkEgressGuardrail`, `RateLimitGuardrail`, `Violation`,
`append_violation`, `default_violation_log_path`, `read_cc_session`,
`resolve_cc_session_path`, `ToolUseCorrectnessScorer`,
`TrajectoryLengthScorer`, `GuardrailComplianceScorer`).

## Context

pyarnes is a library that adopters pin by git ref (`pyarnes_ref` in their `pyproject.toml`). Adopters A (PII redaction), B (S3 sweep), and C (RTM+Toggl→agile) all build on the same public symbols across `pyarnes-core`, `pyarnes-harness`, `pyarnes-guardrails`, and `pyarnes-bench`. Today these packages export what they export without an explicit contract — which means any internal rename can silently break every adopter's `uv sync`.

This spec does not change behaviour. It declares — in code and in docs — which symbols adopters may depend on, which are private, how we version, and how we communicate breaking changes. All downstream specs (02–05) assume this contract exists.

Source plan: `/root/.claude/plans/as-an-expert-in-mellow-whisper.md` — see the "Meta-use" table and "Contributor docs" table for the full symbol inventory.

## Goals / Non-goals

**Goals**

- Publish a reviewed public API surface across the four runtime packages.
- Audit and tighten each package's `__all__` so `from pyarnes_* import *` only yields public names.
- Add a repo-root `CHANGELOG.md` with a semver policy adopters can rely on.
- Mark explicitly-private surfaces (`_call_tool` internals, log-event string names, capture-file JSONL field order, the `Lifecycle.history` list type) so contributors know what is safe to refactor.

**Non-goals**

- Refactoring or renaming existing public symbols. If something is misnamed, leave it — breakages belong in a separate spec with a migration story.
- Touching `pyarnes-tasks`. It is dev-only and not consumed as a library; its contract is the CLI surface (covered by Spec 02).
- Runtime behaviour changes. This is a declarative spec.

## Proposed design

### Stable public surface

| Package | Exports (enforced via `__all__`) |
|---|---|
| `pyarnes_core` | `Lifecycle`, `Phase`, `Budget`; errors `TransientError`, `LLMRecoverableError`, `UserFixableError`, `UnexpectedError`, `HarnessError`, `Severity`; types `ToolHandler`, `ModelClient`; observe `get_logger`, `configure_logging`, `LogFormat`. |
| `pyarnes_harness` | `AgentLoop`, `LoopConfig`, `ToolMessage`, `ToolRegistry`, `ToolCallLogger`, `ToolCallEntry`, `OutputCapture`, `CapturedOutput`; transcript adapter `read_cc_session`, `resolve_cc_session_path`; re-exported guardrails `Guardrail`, `GuardrailChain`, `PathGuardrail`, `CommandGuardrail`, `ToolAllowlistGuardrail`. |
| `pyarnes_guardrails` | `Guardrail`, `GuardrailChain`, `PathGuardrail`, `CommandGuardrail`, `ToolAllowlistGuardrail`, `SecretLeakGuardrail`, `NetworkEgressGuardrail`, `RateLimitGuardrail`; sidecar `Violation`, `append_violation`, `default_violation_log_path`. |
| `pyarnes_bench` | `EvalSuite`, `EvalResult`, `Scorer`, `ExactMatchScorer`, `ToolUseCorrectnessScorer`, `TrajectoryLengthScorer`, `GuardrailComplianceScorer`. |

`Lifecycle` also exposes `.budget` + `.dump(path)` + `.load(path)` for
the Claude Code `SessionStart` / `SessionEnd` hooks.

### Explicitly private

- `AgentLoop._call_tool`, `AgentLoop._dispatch`, and any `_`-prefixed helper.
- Log event string names (`"tool.pre"`, `"guardrail.command_blocked"`, etc.) — treat as internal telemetry; adopters should not regex them.
- `ToolCallLogger` JSONL field order (stable set of *fields*, not stable *order*).
- `Lifecycle.history` concrete list type — the iterable contract is stable, mutations are not.

### Files touched

- `packages/core/src/pyarnes_core/__init__.py` — add `__all__`.
- `packages/harness/src/pyarnes_harness/__init__.py` — add `__all__`.
- `packages/guardrails/src/pyarnes_guardrails/__init__.py` — add `__all__`.
- `packages/bench/src/pyarnes_bench/__init__.py` — add `__all__`.
- `CHANGELOG.md` at repo root — new. Keep-a-Changelog format: `Unreleased / Added / Changed / Deprecated / Removed / Fixed`. Seed with `0.0.0 — initial stable surface declared`.
- `docs/development/evolving.md` — append a "Stable API surface" section listing the table above and the private list. (Full page overhaul is Spec 05; only this section lands here.)

### Semver policy (goes in `CHANGELOG.md` preface)

- MAJOR — removing or renaming anything in the tables above, changing a `ToolHandler`/`Guardrail`/`Scorer` base-class signature, changing error-class inheritance.
- MINOR — new public symbols, new optional kwargs, new `Phase` values, new built-in `Guardrail`/`Scorer` subclasses.
- PATCH — bug fixes, docstring changes, private-surface refactors.

### `__all__` enforcement

Add a test per package: `from pyarnes_<pkg> import *; assert set(dir()) >= set(__all__)` plus a reverse check that every `__all__` entry resolves. Keeps drift visible in CI.

## Tests / acceptance

- `packages/core/tests/test_public_api.py` (and one per package) asserts every `__all__` entry imports cleanly and nothing private leaks via star-import.
- `packages/core/tests/test_error_taxonomy.py` asserts the four error classes exist, their inheritance is unchanged, and they're re-exported from the top-level package.
- `packages/harness/tests/test_public_api.py` additionally asserts `AgentLoop`, `LoopConfig`, `ToolHandler`, `ToolRegistry`, `ModelClient`, `ToolCallLogger` are importable at top level.
- A monorepo-level test (`tests/unit/test_stable_surface.py`) imports every symbol from every table above and fails loudly if any goes missing — this is the regression net adopters implicitly depend on.
- `uv run tasks check` clean (lint + typecheck + test).

## Open questions

- Do we pin Python versions in the stability contract, or declare "support follows `pyproject.toml`'s `requires-python`"? Leaning latter.
- Should `ToolCallLogger` JSONL schema be documented with a schema file (`docs/api/capture-schema.json`) so adopters can diff against it? Defer unless an adopter asks.
- Do we need a deprecation decorator (`@deprecated`) now or is "note in CHANGELOG" enough for the first removal cycle? Defer until we have one to deprecate.

Next: `02-template-adopter-scaffold.md`
