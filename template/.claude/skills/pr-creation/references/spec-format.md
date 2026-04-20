# PR Spec Format Reference

All PR specs live in `specs/PR-NN-*.md`. Each spec is the **source of truth** for a PR's implementation — branch name, dependencies, commit plan, and verification commands.

---

## Metadata Table

Every spec starts with an H1 title and a metadata table:

```markdown
# PR-15-A: TODO Cleanup — Standalone TODOs

| Field | Value |
|-------|-------|
| **Branch** | `feat/0.2.25a-todo-cleanup` |
| **Tier** | 2 — Decomposition & CLI Refactoring |
| **Source PRD** | [refactoring-plan-v2.md](../old_specs/refactoring-plan-v2.md) |
| **Depends On** | PR-12 |
| **Estimated Size** | ~200 LOC changed |
| **Test Freeze** | **Category A — KEPT** (no new public API) |
```

### Required Fields

| Field | Description | How Agents Use It |
|-------|-------------|-------------------|
| **Branch** | Git branch / jj bookmark name | `create-pr-branch.sh <value>` |
| **Depends On** | Upstream PR(s) that must be merged first | Verify merged before starting |
| **Estimated Size** | Approximate LOC changed | Decide Mode A vs Mode B |
| **Test Freeze** | Test modification policy for this PR | Enforce test freeze constraints |

### Optional Fields

| Field | Description |
|-------|-------------|
| **Tier** | Roadmap tier (1-4) |
| **Source PRD** | Link to the source PRD document |
| **Root Evidence** | Links to task_plan.md, progress.md, findings.md |
| **TS-Refactoring Rules** | Link to applicable refactoring rules |

---

## Body Sections

### Summary

Brief description of what the PR does and why.

```markdown
## Summary

Address the remaining standalone TODOs from Stream B that were not absorbed by Stream C.
```

### Implementation Checkpoint

Progress tracking section updated by agents during implementation. Contains:
- **Progress table**: Workstream items with completion status
- **Current State**: What's been done, what's blocked
- **Files Changed**: Files created/modified/deleted per commit
- **Remaining Work**: Checklist of outstanding items

```markdown
## Implementation Checkpoint

### Progress (Completed)

| Workstream | Status | Notes |
|---|---|---|
| Branch created & rebased | ⬜ | |
| Commit 1: refactor(subeditor) | ⬜ | |
| Dev Gate green | ⬜ | |
```

### Commit Plan

Exact commit messages, file scopes, and ordering. Agents must follow this exactly.

```markdown
## Commit Plan

### Commit 1: `refactor(subeditor): address standalone TODOs`
- Items 1-11 in subeditor package
- Files: `packages/subeditor/src/*.ts`

### Commit 2: `refactor: address standalone TODOs in image/diagramming/pdf`
- Items 12-18 across packages
```

### Findings

Rules, constraints, and "Do NOT" directives discovered during spec creation.

```markdown
## Findings

- F-PR15A-01: `Number(x.toFixed(2))` found in 9 instances — replace with `round()` from core/math
- F-PR15A-02: Do NOT create `core/dates` — use `core/utils` to avoid domain sprawl
```

### Verification

Gate commands to run after implementation. Agents execute these exactly.

```markdown
## Verification

### Quick Smoke Check (after each commit)
make toolbox-typecheck

### Full Verification (before PR submission)
make toolbox-typecheck
make toolbox-check
make toolbox-ci-all
git diff main..HEAD -- toolbox/__tests__/ | head -20  # test freeze check
```

---

## Parsing Guidance for Agents

1. **Find the spec**: `ls specs/PR-${NUMBER}-*.md`
2. **Extract Branch**: Look for `**Branch**` row in the metadata table, extract the backtick-quoted value
3. **Extract Depends On**: Look for `**Depends On**` row, parse comma-separated PR references
4. **Extract Commit Plan**: Find `## Commit Plan` section, each `### Commit N:` is one commit
5. **Extract Verification**: Find `## Verification` section, run commands exactly as written

**HALT rules**:
- If no spec file found for the given PR number
- If Branch field is missing or empty
- If Depends On references unmerged PRs
- If Commit Plan section is missing

---

## Naming Convention

Spec files follow the pattern: `PR-NN-short-description[-suffix].md`

- `NN` — PR sequence number (zero-padded for sorting is optional)
- `short-description` — kebab-case topic
- `suffix` — optional session marker (`-a`, `-b`, `-c` for multi-session specs)

Examples:
- `PR-15-todo-cleanup-a.md` — first session of PR-15
- `PR-28-C-vigia-bootstrap-pipeline.md` — current file path for the first session of PR-28
- `PR-29-C-vigia-mcp-ci.md` — current file path for the third session of PR-29
