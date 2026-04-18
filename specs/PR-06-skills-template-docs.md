# PR-06 — Claude Code Skills, Template Integration, Docs

## Context

Final PR. Closes the loop by delivering the **end-user surface**: four Claude
Code skills (`/overview`, `/impact`, `/patch`, `/ship`) that drive the graph
tools from PR-04 and consume the `GRAPH_REPORT.md` + eval data from PR-03 and
PR-05. Wires the PreToolUse hook into `template/.claude/settings.json` so new
adopters get the feature activated by default. Extends `scripts/smoke-template.sh`
to verify all of this lands intact. Adds three targeted doc pages.

After this PR, a new adopter running `copier copy` + `uv sync` gets the full
graph feature with zero manual config.

## Scope

**In**

- Four `SKILL.md` files under `template/.claude/skills/` following the
  convention established by the existing `python-test/SKILL.md` (YAML
  frontmatter + "When this skill activates / What the skill does" sections).
- `template/.claude/settings.json` edit to register the PreToolUse hook.
- `scripts/smoke-template.sh` extensions asserting the four SKILL files
  exist in a freshly-generated project.
- Doc pages:
  - `docs/development/graph.md` — user-facing "how to use the graph" page.
  - Short sections added to `docs/development/tasks.md`,
    `docs/development/testing.md`, `docs/development/evolving.md`.
- Integration test: `tests/features/skills.feature` scenario covering
  a full `/overview` → graph-tool-call → model-response flow using a stubbed
  `ModelClient`.

**Out**

- Any runtime code changes to `pyarnes-graph` / `pyarnes-bench` — all runtime
  work landed in PR-01 through PR-05.
- Cross-language extractors — deferred in the parent plan's "Out of Scope".

## Files

### New

- `template/.claude/skills/overview/SKILL.md` — drives `graph:report` +
  `GetNodeTool` to produce a high-level architecture briefing.
- `template/.claude/skills/impact/SKILL.md` — drives `BlastRadiusTool` to
  estimate the blast radius of a proposed change.
- `template/.claude/skills/patch/SKILL.md` — drives `ShortestPathTool` +
  `GetNeighborsTool` to localize a patch before writing code.
- `template/.claude/skills/ship/SKILL.md` — runs `graph:ci` and summarizes
  pass/fail; blocks ship on reduction-floor failure.
- `docs/development/graph.md` — user-facing guide: install, index, query,
  skills, MCP, and the four Claude Code commands.
- `tests/features/skills.feature` — BDD scenarios for each skill.
- `tests/features/steps/skills_steps.py`

### Modified

- `template/.claude/settings.json` — register PreToolUse hook entry pointing
  at `pyarnes_graph.hooks.pretooluse`. Keeps any existing hooks; appends.
- `scripts/smoke-template.sh` — `assert_exists` for each new SKILL.md and a
  `grep` assertion for the hook registration in settings.json.
- `docs/development/tasks.md` — adds a "Graph tasks" section listing
  `graph:index`, `graph:watch`, `graph:report`, `graph:eval`, `graph:usage`,
  `graph:ci`.
- `docs/development/testing.md` — adds a "Graph test fixtures" section.
- `docs/development/evolving.md` — adds a "Skill placement convention"
  section describing the `template/.claude/skills/<name>/SKILL.md` layout
  that `python-test` established.
- `mkdocs.yml` — adds `development/graph.md` to nav.
- `README.md` — one-line mention of the graph feature with a link to the
  new docs page.

## Reuse

| Existing utility | File | Used for |
|---|---|---|
| Existing SKILL convention | `template/.claude/skills/python-test/SKILL.md` (from commit `ad35cf9`) | YAML frontmatter + section header shape — copied verbatim for the four new skills. |
| Existing hook directory | `.claude/hooks/.gitkeep` | PreToolUse hook lands here with zero setup. |
| `scripts/smoke-template.sh` | root | Add assertions next to the existing `assert_exists` calls — no new script. |
| `docs/development/*` | from commit `ad35cf9` | Append to existing pages rather than introducing new ones (except the main `graph.md`). Three small edits > one large new doc. |
| `pyarnes_graph.tools.*` | PR-04 | Skills call tools via the MCP server registered by the template settings.json. |
| `EvalSuite.summary()` | PR-05 | `/ship` skill reads `.pyarnes/eval/graph-token-reduction.jsonl` and renders the summary. |

## Design notes

1. **Skill contract per file**: YAML frontmatter lists the tools the skill
   needs; body describes activation triggers and expected behaviour. Keeps
   parity with the `python-test` skill so any contributor reading one
   understands all of them.
2. **`/overview` is read-only.** Never writes files, only queries the graph
   and emits a briefing to the transcript. Matches the "overview" semantic
   from the plan.
3. **`/impact` takes a symbol name or file path.** Resolves to a
   `GraphNode.id` via `GetNodeTool` (with the fuzzy match from PR-04), then
   runs `BlastRadiusTool` in both directions.
4. **`/patch` is exploration, not editing.** It plans the location of the
   change and the nearby code the model should read first; the actual edit
   still uses `Write`/`Edit` after the model has the context.
5. **`/ship` is gating.** Runs `graph:ci`. If CI fails (reduction floor
   breach, test failure), the skill emits a structured report and asks the
   user whether to proceed — not a hard block, but loud.
6. **Hook registration is additive.** `template/.claude/settings.json` uses
   a JSON array for hooks; we append rather than replace, so adopters who
   customize settings don't lose their own hooks on regeneration.
7. **Smoke script**: `assert_exists "$OUT/.claude/skills/overview/SKILL.md"`
   plus three siblings + a `grep -q pyarnes_graph.hooks.pretooluse
   "$OUT/.claude/settings.json"`. Short, precise.

## Acceptance

```bash
# From a fresh scratch dir, generate a template project and verify skills land
bash scripts/smoke-template.sh
# Expect: all assert_exists pass.

# In a real Claude Code session inside a generated project:
#   /overview    → produces a briefing (< 30s on a 1k-file repo)
#   /impact foo  → blast-radius table for symbol `foo`
#   /patch "add logging to X"  → plan with pointer to fewer than 5 files
#   /ship        → runs graph:ci; reports reduction ratio and test pass rate

# BDD
uv run pytest tests/features/skills.feature
# Expect: 4 scenarios pass.
```

Docs:

- `mkdocs serve` renders `development/graph.md` with a navigation entry.
- README's one-line link resolves on GitHub.

## Risks & rollback

- **Risk**: Hook registration breaks adopters who have heavily customized
  their `settings.json`. **Mitigation**: the edit is additive-only; smoke
  script includes a case where a pre-existing hook is preserved.
- **Risk**: Skills reference tool names that don't match PR-04's final
  registration. **Mitigation**: the BDD suite in this PR exercises the
  end-to-end flow — mismatches fail loudly in CI.
- **Rollback**: revert; PR-01 through PR-05 remain intact and the graph
  feature is still usable via `uv run tasks graph:*` — only the Claude Code
  surface disappears.

## Exit criteria

- [ ] Four SKILL.md files exist with YAML frontmatter and match the
  `python-test` layout.
- [ ] `scripts/smoke-template.sh` passes on a clean checkout.
- [ ] `mkdocs serve` shows the new graph docs page in nav.
- [ ] BDD scenarios for all four skills pass.
- [ ] In a live Claude Code session, `/overview` produces a non-empty briefing
  within 30s on a 1k-file repo.
- [ ] `uv run tasks check` green across the whole monorepo.
