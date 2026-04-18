# 03 — Reference adopters A (PII redaction) and B (S3 sweep)

## Context

Spec 01 declared the stable API surface. Spec 02 shipped a Copier template that produces starter stubs. This spec builds two **full-fidelity reference implementations** — enough to prove that the library-first posture works end-to-end for the two common shapes the plan calls out: a content-processing pipeline (Adopter A) and a destructive infrastructure sweep (Adopter B). Adopter C (with meta-use) is Spec 04.

These examples double as regression tests. If the stable surface breaks, these examples fail, and we see it before any real adopter does.

## Goals / Non-goals

**Goals**

- Two working reference projects: `packages/examples/pii-pipeline/` and `packages/examples/s3-sweep/`.
- Each uses only the symbols declared stable in Spec 01. No private imports.
- Each ships a Typer CLI, project-specific `ToolHandler` subclasses, custom `Guardrail`s, unit tests, and one pytest-bdd feature test covering the golden path.
- Adopter B's destructive `delete_bucket` path is gated by a `VerificationCompleteGuardrail` that is itself unit-tested against corrupted-manifest inputs.

**Non-goals**

- Reference implementations of Adopter C — Spec 04.
- Publishing these examples to PyPI — they're in-tree demos, not distributable packages.
- Production hardening (retry budgets beyond what `TransientError` already gives us, metrics, tracing). Keep examples minimal.

## Proposed design

### Layout decision: in-tree under `packages/examples/`

Reasoning: CI already runs `uv run tasks check` across the monorepo; in-tree examples get regression coverage for free. Sibling repos would require cross-repo CI plumbing and a second pin of `pyarnes_ref`. Trade-off: the monorepo grows. Acceptable — the examples are small and static.

Add `packages/examples/` to the workspace members list in root `pyproject.toml`. Each example has its own `pyproject.toml` and depends on sibling pyarnes packages via workspace deps (not git URLs — that's the adopter story, not the monorepo story).

### Adopter A — `packages/examples/pii-pipeline/`

**Purpose:** PDF → text extraction → PII detection → redaction → markdown → TF-IDF keyword extraction.

Key files:

- `src/pii_pipeline/cli.py` — Typer app with `ingest <path>` and `redact <path>` subcommands.
- `src/pii_pipeline/pipeline.py` — `async def run_pipeline(input_path, output_path)`; builds `ToolRegistry`, composes `GuardrailChain([PIIGuardrail(), ...])`, runs `AgentLoop`.
- `src/pii_pipeline/tools/pdf.py` — `KreuzbergExtractHandler(ToolHandler)`.
- `src/pii_pipeline/tools/pii.py` — `PresidioRedactHandler(ToolHandler)`.
- `src/pii_pipeline/tools/markdown.py` — `MarkdownRenderHandler(ToolHandler)`.
- `src/pii_pipeline/tools/tfidf.py` — `TfidfKeywordsHandler(ToolHandler)`.
- `src/pii_pipeline/guardrails.py` — `PIIGuardrail(Guardrail)` that scrubs PII from tool-call log entries before `ToolCallLogger.log_call` persists them.
- `tests/unit/test_redaction.py` — feed in a PDF with known PII, assert output contains none.
- `tests/features/redaction_pipeline.feature` — Gherkin scenario for the golden path.

Runtime deps: `kreuzberg`, `presidio-analyzer`, `presidio-anonymizer==2.2.354`, `spacy`, `scikit-learn`, `typer`.

### Adopter B — `packages/examples/s3-sweep/`

**Purpose:** List S3 bucket → download all objects → verify each → **only then** delete bucket. The verification gate is the whole point.

Key files:

- `src/s3_sweep/cli.py` — Typer app with `download`, `verify`, `sweep` subcommands.
- `src/s3_sweep/pipeline.py` — builds the loop; wires `VerificationCompleteGuardrail` and `BucketAllowlistGuardrail` into the chain.
- `src/s3_sweep/tools/s3.py` — four handlers: `ListObjectsHandler`, `DownloadObjectHandler`, `VerifyObjectHandler` (size + etag + xxhash), `DeleteBucketHandler`.
- `src/s3_sweep/guardrails.py`:
  - `VerificationCompleteGuardrail` — reads the verification manifest; blocks `delete_bucket` if any entry is unverified or has a checksum mismatch. Raises `UserFixableError` with a diff of failing keys.
  - `BucketAllowlistGuardrail` — blocks any S3 tool targeting a bucket not in the allowlist.
- `tests/unit/test_verify.py` — inject a corrupt checksum into the manifest, assert `delete_bucket` is blocked with a `UserFixableError`.
- `tests/features/s3_sweep.feature` — Gherkin: list → download → verify → sweep, run against a LocalStack fixture.

Runtime deps: `boto3`, `aioboto3`, `typer`, `xxhash`.

### Fixtures

- `packages/examples/pii-pipeline/tests/fixtures/sample.pdf` — small PDF with known PII.
- `packages/examples/s3-sweep/tests/fixtures/localstack-compose.yml` + a `conftest.py` that spins up LocalStack via `testcontainers` for the feature test.

### What the examples intentionally show

- Every `ToolHandler` subclass body is under 30 lines — the pyarnes surface does the heavy lifting.
- `GuardrailChain.check(tool, args)` is called **explicitly** in `pipeline.py` dispatch — reinforcing the plan's "AgentLoop does not auto-apply guardrails" contract.
- `ToolCallLogger` is instantiated once per run, writes to `logs/tool_calls.jsonl`, and is asserted against in the feature tests.

## Tests / acceptance

- `uv run --package pii-pipeline pytest` green.
- `uv run --package s3-sweep pytest` green (LocalStack required — skipped with clear message if Docker unavailable).
- `uv run --package pii-pipeline pii-pipeline ingest tests/fixtures/sample.pdf` produces redacted output with zero PII matches on a second Presidio pass.
- `uv run --package s3-sweep s3-sweeper download --bucket test-bucket --dest ./out && s3-sweeper verify && s3-sweeper sweep` completes without error on a clean LocalStack; the same sequence with a corrupt manifest exits non-zero with a `UserFixableError`.
- `logs/tool_calls.jsonl` for Adopter B contains every `download_object` + `verify_object` entry **before** any `delete_bucket` entry (ordering assertion).
- `uv run tasks check` at repo root green (examples participate in monorepo CI).
- Neither example imports anything outside the Spec 01 stable surface — enforced by `grep` in a CI step.

## Open questions

- Do we pin Presidio's `presidio-anonymizer==2.2.354` in the template (Spec 02) or only in this example? Template pins it because Adopter A inherits it; document the rationale in `docs/template.md` (Spec 05).
- LocalStack in CI: worth the flake cost, or mock boto at the handler level? Leaning LocalStack for the feature test, mock for unit tests.
- Should Adopter A also ship a `pyarnes-bench` evaluation suite (precision/recall against a labeled corpus)? Yes — add under `tests/bench/`; keep the labeled corpus tiny (10 docs) to stay fast.

Next: `04-template-adopter-c-meta-use.md`
