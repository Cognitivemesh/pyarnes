# 03 — Shape references: pii-redaction and s3-sweep

## Context

Spec 01 declared the stable API surface. Spec 02 shipped the Copier template with four `adopter_shape` choices. This spec documents the **design rationale** for two of those shapes — `pii-redaction` (content processing) and `s3-sweep` (destructive infra). Adopter C (`rtm-toggl-agile` + meta-use) is covered in Spec 04.

**Earlier draft note.** An earlier iteration shipped these patterns as in-tree `packages/example-*/` workspace members so CI would regression-test them. That approach was reverted: the shipped shapes are stamped by the Copier template directly (`template/src/{{project_module}}/…`), and Spec 02's scaffold tests (`tests/template/test_scaffold.py`) validate the rendered output. Carrying a second copy in `packages/example-*/` duplicated intent without adding coverage. The design rationale below is the remaining artefact worth preserving.

## Goals / Non-goals

**Goals**

- Two pattern references that explain *why* each shape makes the choices it makes.
- Each pattern uses only symbols declared stable in Spec 01 — no private imports.
- Each pattern defines its `Typer` CLI, project-specific `ToolHandler` subclasses, custom `Guardrail`s, and one behavioural test covering the golden path.
- The `s3-sweep` shape's destructive `delete_bucket` path is gated by `VerificationCompleteGuardrail`, itself testable against corrupted-manifest inputs.

**Non-goals**

- Reference implementations of the `rtm-toggl-agile` shape — Spec 04.
- Shipping the patterns as installable packages — the Copier template is the delivery mechanism.
- Production hardening beyond what `TransientError` already gives (no retry budgets, metrics, tracing).

## Shape: `pii-redaction`

**Purpose:** PDF → text extraction → PII detection → redaction → markdown → TF-IDF keyword extraction.

Generated layout (under `src/{project_module}/`):

- `cli.py` — Typer app with `ingest <path>` and `redact <path>` subcommands.
- `pipeline.py` — `async def redact(input_path, *, title, allowed_roots)`; builds `ToolRegistry` **once**, composes `GuardrailChain([PathGuardrail, ToolAllowlistGuardrail, PiiLeakGuardrail])`, dispatches tools inline so readers see the three-part contract (register → compose → dispatch) without a helper hiding it.
- `tools/__init__.py` — four `ToolHandler` subclasses: `ExtractText` (Kreuzberg wrapper), `DetectPii` (regex allowlist + optional Presidio), `RedactPii`, `RenderMarkdown`.
- `guardrails.py` — `PiiLeakGuardrail(Guardrail)` that refuses tool calls whose arguments contain PII-shaped strings (scrubs before `ToolCallLogger` persists them).
- `tests/test_redaction.py` — feeds a document with known PII and asserts the output contains none; exercises the `ToolAllowlistGuardrail` rejection path.

Runtime deps the template adds: `kreuzberg`, `presidio-analyzer`, `presidio-anonymizer==2.2.354`, `spacy`, `scikit-learn`, `typer`.

### Design notes

- `build_registry(...)` runs **once** per pipeline call and is threaded into `build_guardrail_chain(registry, allowed_roots=…)`. An earlier draft built three registries per call (once in the chain factory, once in the pipeline, once implicitly) — rolled back during the simplify pass.
- Every `ToolHandler` subclass body stays under 30 lines. The pyarnes surface carries the weight.
- `GuardrailChain.check(tool, args)` is called **explicitly** in `pipeline.py` dispatch — reinforcing the "`AgentLoop` does not auto-apply guardrails" contract from Spec 01.
- Presidio is an optional runtime dep. The default shape ships a regex-allowlist stub so the generated project's tests pass on `uv sync --only-dev` without the Presidio model download.

## Shape: `s3-sweep`

**Purpose:** List S3 bucket → download all objects → verify each → **only then** delete the bucket. The verification gate is the entire point of the shape.

Generated layout:

- `cli.py` — Typer app with `download`, `verify`, `sweep` subcommands; builds the `ToolRegistry` once and threads it through to each stage so the `FakeS3` fixture state persists.
- `pipeline.py` — `download`, `verify`, `sweep` accept an optional pre-built `registry`; each stage composes its own step against a shared registry.
- `tools/__init__.py` — `ListObjects`, `DownloadObject`, `VerifyObject` (size + etag), `WriteManifest`, `DeleteBucket`.
- `guardrails.py`:
  - `VerificationCompleteGuardrail` — reads the manifest; blocks `delete_bucket` if any entry is unverified. Raises `UserFixableError` with the diff of failing keys.
  - `BucketAllowlistGuardrail` — blocks any S3 tool targeting a bucket outside the allowlist.
- `fakes.py` — in-memory `FakeS3` the template ships so the generated project is green before a real boto3 account is wired in.
- `tests/test_pipeline.py` — happy path (download → verify → sweep); adversarial path (corrupt the manifest, assert `UserFixableError`).

Runtime deps the template adds: `boto3`, `aioboto3` (adopter-configured), `typer`.

### Design notes

- **Tool-registry single source of truth.** `cli.py` calls `build_registry(s3=s3)` and passes the resulting `ToolRegistry` into each of the three pipeline stages. Prevents the N+1 registry rebuild that the simplify review caught in an earlier draft.
- **Per-stage logging via `ToolCallLogger`.** Instantiated in `cli.py`, passed into each stage. The JSONL stream at `.pyarnes/tool_calls.jsonl` records every `download_object` + `verify_object` **before** any `delete_bucket` — an ordering invariant a feature test can assert.
- **No real-S3 dependency in-tree.** The generated project ships with `FakeS3` so `uv run pytest` passes offline. Swapping to real boto3 is a one-line change in `cli.py` that replaces `FakeS3()` with an `aioboto3.client("s3")` wrapper.

## Cross-shape invariants

- Every pattern uses only the Spec 01 stable surface. The `tests/unit/test_stable_surface.py` assertion on top-level imports covers this for the monorepo itself; `tests/template/test_scaffold.py` confirms generated projects don't import private submodules either.
- `GuardrailChain` is composed as a Python object — never deserialised from YAML/TOML. This is the non-negotiable design constraint that rules out a generic `pyarnes run --config pipeline.yaml` front end (see Spec 05).
- `ToolCallLogger` is instantiated once per CLI invocation, not per tool call, so a single pipeline run produces one JSONL stream for the auditor.

## Tests / acceptance

- `uv run tasks check` green at repo root — the scaffold tests render both shapes and assert the generated projects have `pyproject.toml`, `CLAUDE.md`, `pipeline.py`, `cli.py`, `guardrails.py`, `tools/__init__.py` with the expected symbols.
- `tests/template/test_scaffold.py::test_shape_specific_deps` asserts that `pii-redaction` pins `presidio-analyzer` and `kreuzberg` in the generated `pyproject.toml`.
- `tests/template/test_scaffold.py::test_blank_has_no_shape_specific_deps` asserts the inverse for `blank`.
- Scaffold tests parametrise over all four shapes (`blank`, `pii-redaction`, `s3-sweep`, `rtm-toggl-agile`) and must pass for each.

## Open questions

- Should the `pii-redaction` shape default to regex-allowlist or to Presidio? Current default: regex. Rationale: the generated project must be green on `uv sync` without downloading 600 MB of Spacy + Presidio models. Adopters that need Presidio flip the import in `tools/__init__.py`.
- `s3-sweep` against real boto3 in CI: worth the flake cost, or keep the `FakeS3` contract-test approach? Leaning `FakeS3` for unit tests; document the boto3 swap-in in `docs/template.md`.
- Should either shape ship a `pyarnes-bench` evaluation suite in `tests/bench/`? Deferred — the `enable_dev_hooks=True` template flag already ships a `tests/bench/test_agent_quality.py` scaffold; adopters populate it when they have a labelled corpus.

Next: `04-template-adopter-c-meta-use.md`.
