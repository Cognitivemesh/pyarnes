# PR-05 — Eval Suite, Scorers, and Usage Tracking

## Context

PR-04 exposed the graph to the model. This PR **proves** the value. We add
two scorers to the existing `pyarnes-bench` package (`TokenReductionScorer`,
`LLMJudgeScorer`), wire them into a reproducible eval suite that runs across
three fixture repos (small, medium, React-like), and add a usage-tracker that
reads the JSONL capture log PR-02 and PR-04 already emit to produce a
`graph:usage` summary. Adds a `graph:ci` composite task so CI can enforce the
token-reduction floor on every PR.

After this PR, we can cite a measured 5×-71× token-reduction number in the
README with CI-verified evidence.

## Scope

**In**

- `bench/scorer.py` extensions: `TokenReductionScorer`, `LLMJudgeScorer`.
- `bench/eval/graph_suite.py` — defines an `EvalSuite("graph-token-reduction")`
  with scenarios for the three fixture repos.
- `tests/fixtures/repos/{small,medium,react_like}/` — canned sample repos
  (tarballs unpacked at test time).
- `graph:eval` task — runs the suite, writes `EvalResult` rows as JSONL.
- `graph:usage` task — aggregates PR-02's + PR-04's JSONL capture logs into a
  per-tool histogram + token-cost estimate.
- `graph:ci` composite task — runs `graph:index` → `graph:eval`, fails if
  median reduction < 5× (the KPI-5 floor from the plan).
- Unit tests for both scorers.

**Out**

- LLM-judge model integration — interface only; the concrete LLM binding is
  injected by callers (Claude API / local Ollama / etc.). We don't ship a
  default network client in this PR (keeps CI offline-capable).
- Skill files consuming the eval results — PR-06.

## Files

### New

- `packages/bench/src/pyarnes_bench/scorer.py` — **extend** (not replace).
  Adds `TokenReductionScorer` and `LLMJudgeScorer` alongside the existing
  `ExactMatchScorer`.
- `packages/bench/src/pyarnes_bench/eval/__init__.py`
- `packages/bench/src/pyarnes_bench/eval/graph_suite.py`
- `packages/bench/src/pyarnes_bench/eval/fixtures.py` — fixture-repo loader.
- `packages/graph/src/pyarnes_graph/usage.py` — JSONL log aggregator.
- `packages/graph/src/pyarnes_graph/tasks.py` — **extend** with
  `graph:eval`, `graph:usage`, `graph:ci`.
- `tests/fixtures/repos/small.tar.gz` (~20 files)
- `tests/fixtures/repos/medium.tar.gz` (~200 files)
- `tests/fixtures/repos/react_like.tar.gz` (~1000 files)
- `tests/unit/bench/test_token_reduction_scorer.py`
- `tests/unit/bench/test_llm_judge_scorer.py` (uses a stub `ModelClient`).
- `tests/unit/graph/test_usage.py`

### Modified

- `packages/bench/pyproject.toml` — add `tiktoken>=0.7` for token counting.
- Root `pyproject.toml` — no new deps at root level.
- Parent plan references "KPI-5: ≥ 5× reduction floor" — enforce it in
  `graph:ci`.

## Reuse

| Existing utility | File | Used for |
|---|---|---|
| `Scorer` ABC | `packages/bench/.../scorer.py:14-29` | Both new scorers subclass this — one `score` method each. |
| `ExactMatchScorer` | `packages/bench/.../scorer.py:31-46` | Reference pattern for `@dataclass(frozen=True, slots=True)`. |
| `EvalResult` | `packages/bench/.../eval.py:19-46` | Token-reduction results use `metadata={"baseline_tokens": ..., "graph_tokens": ..., "reduction_ratio": ...}`. No schema changes. |
| `EvalSuite` | `packages/bench/.../eval.py:49-101` | `graph:eval` returns `suite.summary()` as JSON. Pass-rate + average-score aggregation already done. |
| `ModelClient` ABC | `packages/core/.../types.py:43-60` | `LLMJudgeScorer` takes a `ModelClient` in its constructor — caller wires Claude/OpenAI/stub at the edge. |
| `ToolCallLogger` JSONL format | `packages/harness/.../capture/tool_log.py` | `graph:usage` is a pure reader of files written by PR-02 and PR-04 — **zero writer duplication**. |
| `ToolCallEntry.as_dict()` | same | Deserialization: `json.loads` → dict → `ToolCallEntry(**...)`. |
| `EvalSuite.summary()` | bench | Produces the JSON shape consumed by `graph:ci`'s threshold check. |
| `COMPOSITE_TASKS` | `packages/tasks/src/pyarnes_tasks/cli.py:29-33` | Register `"graph:ci"` as a one-line composite of `["graph:index", "graph:eval"]`. |

## Design notes

1. **`TokenReductionScorer`**: compares two measurements:
   - `baseline_tokens` = naive "read all relevant files" approach — counted
     by globbing the repo and summing tiktoken counts.
   - `graph_tokens` = `GRAPH_REPORT.md` + N graph-tool calls' serialized
     responses, summed via tiktoken.
   - Score = `(baseline - graph) / baseline`, clipped to `[0, 1]`. A 5×
     reduction corresponds to score = 0.8.
2. **`LLMJudgeScorer`** injects `ModelClient`. The judge prompt asks: "does
   `actual` contain enough information to answer the task stated in
   `expected`?" Returns 0.0 / 0.5 / 1.0 based on the model's structured reply.
   The rubric is in `packages/bench/src/pyarnes_bench/prompts/judge.md` so it
   can be edited without code changes.
3. **Fixture repos are tarballs**, not vendored code. Keeps the repo lean and
   dodges licensing concerns for the React-like fixture (synthesized, not
   copied from a real project). `fixtures.py` unpacks to `tmp_path` on demand.
4. **Offline CI default.** `graph:ci` uses only `TokenReductionScorer` by
   default — that scorer needs zero network. `LLMJudgeScorer` is opt-in via
   `uv run tasks graph:eval --with-judge`.
5. **`graph:usage` histogram columns**: tool_name, call_count,
   total_duration_seconds, p50_ms, p99_ms. Produces a markdown table writable
   to `.pyarnes/USAGE.md`.
6. **Threshold in `graph:ci`**: median reduction across fixtures ≥ 0.8 (=
   5×). The weaker-repo-penalty: the smallest fixture must independently
   reach ≥ 0.5 (2×) or the task fails — prevents pass-by-averaging.

## Acceptance

```bash
uv run tasks graph:index .
uv run tasks graph:eval
# Expect: .pyarnes/eval/graph-token-reduction.jsonl with 3 rows,
# pass_rate >= 0.8, average reduction >= 5x.

uv run tasks graph:usage
cat .pyarnes/USAGE.md
# Expect: markdown table with >= 4 tool rows.

uv run tasks graph:ci
# Expect: exit 0 when reduction floor holds; exit non-zero otherwise.
```

Unit checks:

- `test_token_reduction_scorer.py` — synthetic (baseline=1000, graph=100)
  → score 0.9.
- `test_llm_judge_scorer.py` — stub `ModelClient` always returns `{"type":
  "final_answer", "content": "0.75"}`; scorer parses and returns 0.75.
- `test_usage.py` — fixture JSONL with 5 entries → histogram aggregates
  correctly, p99 > p50.

## Risks & rollback

- **Risk**: `tiktoken` has a heavy C extension. **Mitigation**: already in
  widespread use; works on CI runners without issue. Pin compatible version.
- **Risk**: Fixture-repo byte-count drifts cause flaky reduction numbers.
  **Mitigation**: use *relative* reduction (ratio) not absolute; tolerance
  band ±10% around expected score.
- **Risk**: `graph:ci` blocks CI on transient eval flakes. **Mitigation**:
  retry the eval once on failure before declaring CI failure.
- **Rollback**: revert; PR-04's tools remain usable. No adopter consumes the
  eval task yet.

## Exit criteria

- [ ] `graph:eval` produces 3 `EvalResult` rows with reduction ≥ 2× on the
  smallest repo and ≥ 5× median.
- [ ] `graph:usage` summarizes a populated JSONL log into a markdown table.
- [ ] `graph:ci` composite task runs green end-to-end.
- [ ] All new tests green.
- [ ] No regression in `pyarnes-bench` existing tests.
