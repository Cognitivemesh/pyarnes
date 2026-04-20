# Changelog

All notable changes to pyarnes are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

pyarnes is distributed as git-pinned packages, not via PyPI. Adopters pin by
setting `pyarnes_ref` in their Copier answers to a tag name (e.g. `v0.1.0`).
Bumping `pyarnes_ref` and running `uv run tasks update` is how an adopter picks
up a new release.

## Versioning policy

Every public symbol in the tables below is covered by this policy. Anything not
listed, and anything whose name begins with an underscore, is private — it may
be renamed or removed in any release.

**MAJOR** — removing or renaming a public symbol, changing a `ToolHandler`,
`ModelClient`, `Guardrail`, or `Scorer` base-class signature, changing the
inheritance graph of an error class, or altering the `ToolCallLogger` JSONL
field set.

**MINOR** — adding a new public symbol, a new optional keyword argument, a new
`Phase` value, a new built-in `Guardrail`/`Scorer` subclass, or a new
`pyarnes-tasks` subcommand.

**PATCH** — bug fixes, docstring changes, private-surface refactors,
performance improvements that preserve behaviour.

### Public surface (stable)

| Package | Exports |
|---|---|
| `pyarnes_core` | `HarnessError`, `TransientError`, `LLMRecoverableError`, `UserFixableError`, `UnexpectedError`, `Severity`, `Lifecycle`, `Phase`, `LogFormat`, `configure_logging`, `get_logger`, `ModelClient`, `ToolHandler` |
| `pyarnes_harness` | `AgentLoop`, `LoopConfig`, `ToolMessage`, `ToolRegistry`, `Guardrail`, `GuardrailChain`, `PathGuardrail`, `CommandGuardrail`, `ToolAllowlistGuardrail`, `CapturedOutput`, `OutputCapture`, `ToolCallEntry`, `ToolCallLogger` |
| `pyarnes_guardrails` | `Guardrail`, `GuardrailChain`, `PathGuardrail`, `CommandGuardrail`, `ToolAllowlistGuardrail` |
| `pyarnes_bench` | `EvalResult`, `EvalSuite`, `Scorer`, `ExactMatchScorer` |

`pyarnes-tasks` is dev-infrastructure; its contract is the CLI surface
documented in `docs/packages/tasks.md`, not a Python API.

### Private surface (may change without notice)

- Any attribute, method, or module whose name starts with `_`.
- `AgentLoop._call_tool` and any other `_`-prefixed helper on public classes.
- Log event string names (`"tool.pre"`, `"guardrail.command_blocked"`, …) —
  treat as telemetry, not a stable API. Do not regex them in production code.
- `ToolCallLogger` JSONL field *order*. The set of fields is stable; the order
  they appear on disk is not.
- `Lifecycle.history` concrete list type. The iterable contract is stable;
  mutating it is not supported.

## [Unreleased]

### Added

- First declaration of the stable public surface (this file).
- Stability test suite: `tests/unit/test_stable_surface.py` enforces that every
  symbol in the tables above resolves and that no public `__all__` entry is
  silently dropped.
- `tests/unit/test_docs_examples.py` — parses every Python fenced block in
  `docs/**/*.md` to catch syntax errors and undefined names in examples.

### Changed

- Documentation now includes a "Stable API surface" section under
  `docs/development/evolving.md` mirroring this policy for contributor
  discoverability.

### Fixed

- `docs/adopter/build/quickstart.md`: the `ReadFileTool` example now wraps
  `Path.read_text` in `asyncio.to_thread` instead of calling it directly inside
  an `async def`, matching the async-first invariant in `concepts.md`.
- `docs/adopter/build/quickstart.md`: added the missing
  `from pyarnes_core.types import ModelClient` import so Step 2 is copy-paste
  runnable.
- `docs/adopter/build/quickstart.md`: new Step 5 wires `GuardrailChain` into the
  loop via a `register_guarded` helper. Previously `chain.check(...)` was shown
  only in isolation, contradicting the sequence diagram at the top of the page.
- `packages/core/src/pyarnes_core/types.py`: the `ToolHandler` docstring example
  now uses `asyncio.to_thread` too; hover-docs no longer teach the blocking-I/O
  anti-pattern.
- `docs/maintainer/onboard/testing.md`: removed phantom `test_api.py`; added
  four real unit-test files that were missing from the tree.
- `docs/adopter/evaluate/distribution.md`, `docs/maintainer/release.md`: added
  an explicit 0.x stability disclaimer — MINOR releases may break until v1.0.0.
- `CONTRIBUTING.md`: dropped a stale bullet referencing `packages/example-*`
  directories that do not exist.

## [0.0.0] - 2026-04-18

- Initial stable surface declared. No behaviour changes; this tag anchors the
  semver policy above. Adopters pinning `pyarnes_ref = "v0.0.0"` can rely on
  every symbol in the public-surface table to remain available until the next
  MAJOR release.
