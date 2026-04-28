---
persona: adopter
tags: [adopter, build, bench, codeburn, observability]
---

# AI spend (codeburn)

`pyarnes-bench` ships a CodeBurn-style observability layer on top of the token
visibility primitives. Three CLI tasks turn local Claude Code transcripts into
KPIs, A/B comparisons, and a rank-ordered list of waste-detection findings —
without any extra LLM calls.

| Task                  | What it does                                                              |
| --------------------- | ------------------------------------------------------------------------- |
| `burn:report`         | Per-project token + cost summary (existing).                              |
| `codeburn:kpis`       | Per-session KPIs: one-shot rate, retry loops, cache-hit rate, ratios.     |
| `codeburn:compare`    | A/B side-by-side for two models.                                          |
| `codeburn:optimize`   | Seven detectors → ranked findings → A–F health grade with 48 h trend.    |

All input comes from `~/.claude/projects/<slug>/*.jsonl`. The only network
dependency is LiteLLM's pricing table.

## Quick start

```bash
uv run tasks burn:report                              # token + cost
uv run tasks codeburn:kpis -- --format json           # KPIs (machine-readable)
uv run tasks codeburn:compare -- --a sonnet --b opus  # A/B model comparison
uv run tasks codeburn:optimize                        # waste scan + grade
```

Each task exits 0 on success. `codeburn:optimize --strict` exits 1 when the
grade is D or F (CI use case).

## KPI definitions

| KPI                 | Definition                                                                          |
| ------------------- | ----------------------------------------------------------------------------------- |
| `one_shot_rate`     | Fraction of `Edit`/`Write` calls not followed by another edit on the same path or by a failing `Bash` test in the next 6 calls. |
| `retry_loops`       | Count of `failing-Bash → Edit → succeeding-Bash` triples.                          |
| `cache_hit_rate`    | `cache_read / (cache_read + cache_creation + input)` tokens.                        |
| `read_edit_ratio`   | `Read calls / Edit calls`. `-1` when there are no edits but reads exist.            |
| `cost_by_bucket`    | Total cost split across the 13 task buckets (CODING, DEBUGGING, …).                |

Sums are additive across sessions, so a project total is just the sum.

## Health grade

| Grade | Severity score | Meaning                                                |
| ----- | -------------- | ------------------------------------------------------ |
| A     | 0              | No findings.                                           |
| B     | 1–3            | One LOW or MEDIUM issue.                               |
| C     | 4–9            | A handful of MEDIUMs, or a HIGH.                       |
| D     | 10–19          | Multiple HIGHs — investigate.                          |
| F     | 20+            | Critical waste pattern; fix before continuing.         |

Severity weights: LOW=1, MEDIUM=3, HIGH=7, CRITICAL=12.

## Detectors

| Code                   | Severity | What it flags                                                      |
| ---------------------- | -------- | ------------------------------------------------------------------ |
| `REREAD_FILES`         | MEDIUM   | Same file read ≥3 times across sessions.                           |
| `LOW_READ_EDIT_RATIO`  | HIGH     | Sessions with `reads/edits < 0.5` (blind edits).                   |
| `UNCAPPED_BASH`        | MEDIUM   | Bash result > 16 KiB without `head`/`tail`.                        |
| `UNUSED_MCP`           | LOW      | MCP server in `~/.claude/settings.json` but never called.         |
| `GHOST_AGENTS`         | LOW      | Agent declared but never invoked.                                  |
| `GHOST_SKILLS`         | LOW      | Skill declared but never invoked.                                  |
| `BLOATED_CLAUDE_MD`    | MEDIUM   | `CLAUDE.md` over 16 KiB or with > 5 `@-imports`.                   |
| `CACHE_CHURN`          | LOW      | 20+ call session with no `Read` (cache won't compound).            |

## 48 h trend

Each `codeburn:optimize` run writes a JSON snapshot to
`~/.cache/pyarnes/codeburn/optimize-<isodate>.json` (mode `0o600`, atomic via
`pyarnes_core.atomic_write`). The next run compares against the most recent
snapshot ≤ 48 h old and reports the per-severity delta.

The module is **read-only** with respect to `~/.claude/`: only the cache
directory is written.

## Observability

Every task emits structured events on stderr through
`pyarnes_core.observability`. Pipe stderr through `jq` to inspect:

```bash
PYARNES_LOG_LEVEL=DEBUG uv run tasks codeburn:optimize \
  2> >(jq -c 'select(.event | startswith("codeburn."))')
```

Canonical events: `codeburn.session.parsed`, `codeburn.dedupe.dropped`,
`codeburn.classify.summary`, `codeburn.kpis.computed`,
`codeburn.compare.completed`, `codeburn.optimize.finding`,
`codeburn.optimize.report`, `codeburn.snapshot.written`.

Stdout is reserved for the rendered table or `--format json` payload.
