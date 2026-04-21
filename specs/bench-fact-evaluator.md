# bench-fact-evaluator

Contract for the post-hoc FACT (Factual Abundance and Citation
Trustworthiness) evaluator shipped in `pyarnes-bench`.

Mirrors the style of `specs/bench-scorer-verdict.md` and
`specs/bench-race-evaluator.md`.

## Context

Long-form research reports cite sources; adopters need to know whether
those citations actually support the claims attached to them.
DeepResearch Bench's FACT framework operationalises this as two
numbers:

- **Citation accuracy** = supported / (supported + unsupported) over
  the deduplicated claim list.
- **Effective citations** = absolute count of supported claims —
  rewards reports that cite more when cited well. Reported as a
  cross-task mean.

FACT is post-hoc: it runs after the agent has emitted its report and
the adopter has fetched the cited pages. This spec ships it as a
library-only addition; the Claude Code plug-in wrapping it is captured
as a separate deferred spec (`specs/claudecode-pyarnes-judge-plugin.md`).

## Goals / non-goals

**Goals.**

- Ship `FactEvaluator` in `packages/bench/src/pyarnes_bench/fact.py`.
- Ship Pydantic v2 result models: `FactMetrics`, `CitationClaim`,
  `FactPrompts`. Ship the `Sources` type alias and the
  `effective_citations_across` helper.
- Share `_judge.judge_json` with RACE (already added in PR 1).
- Update the stable-surface golden test and CHANGELOG.

**Non-goals.**

- No URL fetching. `sources: Mapping[str, str]` is adopter-prepared.
- No concurrency. One extraction call, then one verification call per
  deduplicated claim. Matches the serial-by-design convention.
- No `Scorer` subclass. Same reasoning as RACE.
- No Claude Code packaging.

## Proposed design

### Inputs

```python
Sources = Mapping[str, str]  # url -> already-fetched content

class FactEvaluator:
    def __init__(self, client: ModelClient, *, prompts: FactPrompts | None = None) -> None: ...

    async def evaluate(self, *, report: str, sources: Sources) -> FactMetrics: ...
```

### Pipeline

1. **Extraction.** One judge call returns `{"claims": [{"statement",
   "url"}, ...]}`. Parsed into private `_ExtractedClaim` Pydantic
   instances.
2. **Dedup.** Exact `(statement, url)` pairs collapse; near-duplicate
   statements sharing the same URL collapse when
   `difflib.SequenceMatcher.ratio() >= 0.97` (stdlib; zero new dep).
3. **Verification.** For each remaining pair in a plain `for` loop:
   - If `sources[url]` is absent → emit
     `CitationClaim(supported=None, reason="source_not_provided")`.
   - Else → one judge call with
     `{"supported": bool, "reason": str}`; emit
     `CitationClaim(supported=..., reason=...)`.
4. **Aggregate.**
   - `total = count(supported is not None)`
   - `supported = count(supported is True)`
   - `citation_accuracy = supported / total` (0.0 if `total == 0`)
   - `effective_citations = supported`

### Result models (Pydantic v2, frozen, `extra="forbid"`)

```python
class CitationClaim(BaseModel):
    statement: str              # non-empty
    url: str                    # non-empty
    supported: bool | None
    reason: str

class FactMetrics(BaseModel):
    claims: tuple[CitationClaim, ...]
    total: int                  # >= 0
    supported: int              # >= 0, <= total
    citation_accuracy: float    # in [0, 1]
    effective_citations: int    # >= 0, must equal supported
    metadata: dict[str, Any]

    @model_validator(mode="after")
    def _validate_counts(self) -> Self: ...

    def to_eval_result(self, *, scenario: str, threshold: float = 0.8) -> EvalResult: ...
```

`FactPrompts` carries the two overridable templates
(`extraction_prompt`, `verification_prompt`) with placeholders
`{report}`, `{statement}`, `{url}`, `{source}`.

### Helper

```python
def effective_citations_across(metrics: Iterable[FactMetrics]) -> float: ...
```

Free function, not a method — matches DeepResearch Bench's definition
of abundance as a cross-task mean.

## Error taxonomy mapping

| Source                                        | Error raised             |
|-----------------------------------------------|--------------------------|
| Empty `report`                                | `UserFixableError`       |
| Extraction or verification judge returns bad  | `LLMRecoverableError`    |
| JSON persistently (one retry)                 |                          |
| `FactMetrics` constructed with inconsistent   | `ValidationError`        |
| counts (`supported > total`, etc.)            |                          |
| Provider rate-limit / network                 | `TransientError`         |

## File layout

```
packages/bench/src/pyarnes_bench/
  fact.py              # NEW — all public FACT symbols
  __init__.py          # EDIT — re-export
tests/unit/bench/
  test_fact.py         # NEW
tests/features/
  fact_evaluation.feature          # NEW
  steps/test_fact_evaluation.py    # NEW
tests/unit/test_stable_surface.py  # EDIT — add new symbols
specs/bench-fact-evaluator.md      # NEW (this file)
specs/claudecode-pyarnes-judge-plugin.md  # NEW — future-work (deferred)
CHANGELOG.md                       # EDIT — Added entries
docs/adopter/build/benchmarking.md # EDIT — FACT section
docs/maintainer/packages/bench.md  # EDIT — diagram + API row
packages/bench/README.md           # EDIT — one-line mention
```

## Tests / acceptance

- `tests/unit/bench/test_fact.py`:
  - All claims supported → accuracy 1.0, effective == supported.
  - Mixed support → accuracy reflects the supported/total ratio.
  - Missing source → `supported=None`, excluded from denominator.
  - Exact duplicates collapse.
  - Near-duplicates on the same URL collapse (ratio ≥ 0.97).
  - Near-duplicates on *different* URLs do NOT collapse.
  - Empty report → `UserFixableError`.
  - Zero claims → `citation_accuracy == 0.0`.
  - `to_eval_result` threshold routing.
  - `FactMetrics` rejects inconsistent counts.
  - `CitationClaim` rejects empty statement / empty URL.
  - `effective_citations_across` mean + empty-input zero.
- `tests/features/fact_evaluation.feature` + steps: three scenarios
  covering all-supported, missing-source-excluded, empty-report paths.
- `uv run tasks check` and `uv run tasks security` both clean.

## Open questions

- Should near-duplicate dedup be configurable? **Lean:** no —
  exposing a `similarity_threshold` kwarg invites bike-shedding and
  `0.97` is a conservative default that matches the paper's intent.
- Should the verification prompt see the statement's original
  surrounding paragraph for context? **Lean:** no — the paper evaluates
  at statement granularity; whole-paragraph context dilutes the
  judge's signal and inflates the source-length denominator adopters
  pay for.
- Should `FactMetrics` expose `unsupported_count`? **Lean:** no —
  trivially derivable as `total - supported` and keeps the model
  narrow.
