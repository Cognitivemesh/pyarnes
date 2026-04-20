# bench-scorer-verdict

Contract for expanding `pyarnes-bench` scorers with a typed verdict
shape and four new concrete scorers, without breaking the existing
`Scorer` ABC.

Closes **Theme 1** of the `packages/bench/` review (see
`/root/.claude/plans/could-please-review-and-drifting-dongarra.md`).

## Context

`packages/bench/` currently ships a single `ExactMatchScorer` and a
`Scorer` ABC whose only contract is `score(expected, actual) -> float`.
Adopters building coding or deep-agent benchmarks need four things the
library does not offer today:

1. **Fuzzy / regex / numeric** matching (for free-form LLM outputs).
2. An **LLM-as-judge** scorer for qualitative rubrics.
3. A way to carry **reasoning, token counts, cost, and model name**
   out of the scorer — a bare `float` hides too much.
4. A migration path that does **not** break the existing
   `Scorer.score()` signature (stable surface per `CHANGELOG.md`).

Agents-eval (qte77) demonstrates the three-tier taxonomy we are
adapting (see `docs/architecture.md` in that repo). The Tier 1
analogues (`cosine_score`, `jaccard_score`, `semantic_score`) map to
algorithmic scorers; Tier 2 (`technical_accuracy`,
`constructiveness`, `planning_rationality`) maps to the new LLM
judge; Tier 3 is handled by the separate trajectory scorers in
`bench-use-cases-coding-and-deep-agents.md`.

## Goals / non-goals

**Goals.**

- Add `ScorerVerdict` frozen dataclass in
  `packages/bench/src/pyarnes_bench/scorer.py`.
- Add `Scorer.verdict()` as a default-implementing method that wraps
  `self.score(...)` into a `ScorerVerdict`. Subclasses can override.
- Ship four new scorers in the same file: `FuzzyScorer`,
  `RegexScorer`, `NumericToleranceScorer`, `LLMJudgeScorer`.
- Keep `Scorer.score() -> float` unchanged — no breaking change.
- Update the stable-surface golden test to include the new symbols.

**Non-goals.**

- No plugin registry or auto-discovery (forbidden by the "no magic"
  rule in `docs/maintainer/extend/architecture.md`).
- No composite/weighted scorer class — adopters compose scorers
  explicitly in their own code (per `docs/maintainer/packages/bench.md`).
- No fixtures shipped inside `packages/bench/src/` (see Theme 6 in
  the plan file — library-bundled example data is explicitly
  rejected).
- No new top-level package; every symbol lives in `pyarnes_bench`.

## Proposed design

### `ScorerVerdict` (new, frozen dataclass)

```python
from dataclasses import dataclass, field

@dataclass(frozen=True, slots=True)
class ScorerVerdict:
    score: float
    reason: str = ""
    metadata: dict[str, object] = field(default_factory=dict)
```

`score` is always in `[0.0, 1.0]`. `reason` is free-text rationale
(required for `LLMJudgeScorer`, optional for others). `metadata`
carries scorer-specific fields such as `token_in`, `token_out`,
`cost_usd`, `model` for `LLMJudgeScorer`, or `matched_pattern` for
`RegexScorer`.

### `Scorer` ABC — default `verdict()` wrapper

```python
class Scorer(ABC):
    @abstractmethod
    def score(self, expected, actual) -> float: ...

    async def verdict(self, expected, actual) -> ScorerVerdict:
        return ScorerVerdict(score=self.score(expected, actual))
```

The `async` default lets `LLMJudgeScorer` override without forcing
existing synchronous subclasses to change. This also aligns with the
separate async-migration scoped in `harness-loop-budget-hooks.md`.

### New concrete scorers

- **`FuzzyScorer(threshold: float = 0.8)`** — uses
  `difflib.SequenceMatcher.ratio()` on stripped strings. Returns
  `ratio` as score; `reason` = `"fuzzy ratio=<r>"`.

- **`RegexScorer(pattern: str, flags: int = 0)`** — compiles once at
  init. Score = `1.0` if `re.search` matches, else `0.0`. `metadata`
  includes the matched group on success.

- **`NumericToleranceScorer(tolerance: float, relative: bool = False)`** —
  parses `expected` and `actual` as floats; returns `1.0` if within
  tolerance (absolute by default, relative if flag set).

- **`LLMJudgeScorer(client: ModelClient, rubric: str)`** — overrides
  `verdict()` (not `score()`) because it needs async. `rubric` is a
  free-text prompt template with `{expected}`/`{actual}` placeholders.
  Returns structured JSON `{"score": float, "reason": str}` parsed
  from the model response. `metadata` carries `token_in`,
  `token_out`, `cost_usd`, `model`. `ModelClient` is imported from
  `pyarnes_core.types` (already exists — zero new dependencies).

  Three documented rubric strings (not constants, not exported — just
  examples in the docstring):
  - `technical_accuracy` — "Rate technical correctness 0–1..."
  - `constructiveness` — "Rate how actionable the feedback is..."
  - `planning_rationality` — "Given this plan and trace, rate..."

  Names mirror Agents-eval Tier 2 for cross-project familiarity.

### File layout

Only one file changes, plus tests:

```
packages/bench/src/pyarnes_bench/scorer.py   # edited (all new code here)
packages/bench/src/pyarnes_bench/__init__.py # re-export new symbols
tests/unit/test_scorers.py                    # new: parametrized cases
tests/unit/test_stable_surface.py             # edited: golden diff
CHANGELOG.md                                  # add "Added" entry
```

No new files under `packages/bench/src/`.

## Tests / acceptance

- `tests/unit/test_scorers.py` — parametrized coverage:
  - `ExactMatchScorer`: exact hit, exact miss, case differences.
  - `FuzzyScorer`: above threshold, below threshold, empty strings.
  - `RegexScorer`: match, no match, invalid pattern raises at init.
  - `NumericToleranceScorer`: within tol, outside tol, non-numeric
    input → `UserFixableError` from `pyarnes_core.errors`.
  - `LLMJudgeScorer`: mocked `ModelClient` returning valid JSON,
    invalid JSON → `LLMRecoverableError`.

- Stable-surface golden in `tests/unit/test_stable_surface.py` now
  lists `ScorerVerdict`, `FuzzyScorer`, `RegexScorer`,
  `NumericToleranceScorer`, `LLMJudgeScorer` alongside the pre-
  existing entries.

- `uv run tasks check` — lint + typecheck + test all pass.

- `uv run tasks security` — bandit clean (`re.compile` on untrusted
  patterns is fine; `RegexScorer` accepts adopter-provided patterns
  only, no user input path).

## Open questions

- Should `LLMJudgeScorer` retry once on invalid JSON (via the
  `TransientError` path) before surfacing `LLMRecoverableError`?
  **Lean:** yes, single retry — matches the existing retry cap of 2
  documented in `CLAUDE.md` error taxonomy.

- Should the three rubric strings become module-level constants
  (e.g. `RUBRIC_TECHNICAL_ACCURACY`)? **Lean:** no — keep them as
  docstring examples only, so adopters own their prompts (per
  `docs/maintainer/packages/bench.md`: "adopters own their
  scenarios").
