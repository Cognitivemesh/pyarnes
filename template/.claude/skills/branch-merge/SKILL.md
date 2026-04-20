---
name: branch-merge
description: |
  Safely merge feature branches, bookmarks, and stacked changes into main.
  Jujutsu-native with git fallback. Handles jj bookmarks, stacked changes,
  uncommitted work, pre-merge CI validation, push to remote, and cleanup.
  Use when merging branches, recovering detached changes, or cleaning up.
  Keywords: merge, branch, bookmark, jj, jujutsu, stacked, push, cleanup, git.
license: Apache-2.0
metadata:
  author: cognitivemesh.org
  version: "2.2.0"
  execution_policy: on_demand
  priority: normal
  allowed-tools:
    - Bash(git:*)
    - Bash(jj:*)
    - Bash(gh:*)
    - Bash(make:*)
    - Bash(bun:*)
    - Read
    - Edit
  triggers:
    - "merge branch"
    - "merge to main"
    - "merge bookmark"
    - "detached HEAD"
    - "push to main"
    - "clean up branches"
    - "branch status"
    - "bookmark status"
    - "squash changes"
    - "merge PR"
    - "merge pull request"
    - "merge all branches"
    - "update specs after merge"
    - "post-merge cleanup"
  composition:
    required: []
    synergy: ["update-specs"]
    note: "Step 6 updates specs after merge. For mid-implementation spec updates, use update-specs skill directly."
  scripts:
    - scripts/branch-status.sh
    - scripts/safe-merge.sh
    - scripts/pre-merge-validate.sh
    - scripts/cleanup-merged.sh
    - scripts/post-merge-specs.sh
---

# branch-merge

Safely merge feature branches, jj bookmarks, and stacked changes into `main`. Jujutsu-native with automatic git fallback. Automates stash/snapshot, pre-merge validation, fast-forward merge, push, and cleanup.

---

## VCS Detection

All scripts auto-detect the VCS backend:
1. **jj-managed repo** (`.jj/` exists + `jj` binary available): Uses `jj` commands natively
2. **Git-only repo**: Falls back to standard `git` commands

The `agentfs` package provides a typed TypeScript adapter for jj operations (`VigiaRuntime`, `executeJujutsuOperation`). The shell scripts complement this with CLI-level automation.

---

## When to Use This Skill

**Use when:**
- Merging jj bookmarks or git branches into `main`
- Recovering detached HEAD / orphaned jj changes
- Squashing stacked changes before merge
- Cleaning up fully-merged bookmarks/branches
- Pushing local `main` commits to `origin/main`
- Checking bookmark/branch status across the repo

**Do NOT use for:**
- Interactive rebase workflows (use `jj rebase` directly)
- Release tagging or hotfix cherry-picks
- Cross-repo operations
- Mutation testing workflows (use VigiaRuntime)

---

## Prerequisites

| Requirement | Check Command | Required |
|-------------|---------------|----------|
| Git installed | `git --version` | Yes |
| jj installed | `jj version` | Recommended |
| jj repo initialized | `ls .jj/` | Auto-detected |
| Bun installed | `bun --version` | Yes |
| Make targets available | `make help` | Yes |
| Husky hooks configured | `ls .husky/pre-commit` | Yes |

---

## Key Concepts: jj vs git

| Concept | jj Term | git Term |
|---------|---------|----------|
| Named pointer | Bookmark | Branch |
| Current work | Working copy change | Working tree |
| Save work | Automatic (every change is snapshotted) | `git stash` |
| Combine changes | `jj squash` | `git merge --squash` |
| Move changes | `jj rebase` | `git rebase` |
| Push to remote | `jj git push` | `git push` |

---

## Agent Instructions (Behavioral Protocol)

### Step 1: Assess Current State

Run the status script to understand the repo:

```bash
bash .ctx/skills/branch-merge/scripts/branch-status.sh
```

This shows:
- **jj mode**: Current change, bookmarks with tracking status, stacked changes above main
- **git mode**: HEAD state, branches with ahead/behind counts, stash count

> **Squash-merge detection** (from CLAUDE.md): Use `git log --oneline main..<ref>` to detect
> all merges including squash-merges. Empty output means the ref is already in main.
> Do NOT rely on `git branch --merged` alone — it misses squash-merged branches.

### Step 2: Secure Uncommitted Changes

**jj**: No action needed — jj automatically snapshots the working copy. Every change is preserved.

**git fallback**: Stash with a descriptive message:
```bash
git stash push -m "wip: <context> before merge"
```

### Step 3: Pre-Merge Validation

Run CI checks before merging. The script mirrors the canonical CI gate (`ci.yml` → `make toolbox-ci-all`) to catch failures locally before push.

```bash
# Full CI gate: install → build → check → typecheck → tests
# This is what CI runs — use before pushing to main.
bash .ctx/skills/branch-merge/scripts/pre-merge-validate.sh

# Full CI gate + browser tests (exact ci.yml match)
bash .ctx/skills/branch-merge/scripts/pre-merge-validate.sh --browser

# Quick mode: lint + typecheck only (for iterative work during rebase/conflict resolution)
bash .ctx/skills/branch-merge/scripts/pre-merge-validate.sh --quick
```

| Mode | Steps | Matches CI? | When to use |
|------|-------|-------------|-------------|
| (default) | install → build → check → typecheck → tests | Yes (`toolbox-ci-all`) | Before any push to main |
| `--browser` | Same + browser render tests | Exact `ci.yml` match | Before final push (when browser tests matter) |
| `--quick` | lint + typecheck | Subset only | Iterative work, conflict resolution |

> **Note:** `safe-merge.sh` runs the **full CI gate** (install → build → check → typecheck → tests) by default. If you already validated manually in this step, pass `--no-validate` to the merge script to avoid running it twice.
>
> **CI parity rule:** Always run the full gate (no flags) before pushing to main. The `--quick` mode is a convenience shortcut for `pre-merge-validate.sh` during iterative work, not a substitute for CI.
>
> **When to use `--no-validate` at merge time:** If `safe-merge.sh` validation fails due to environment issues (e.g. `bun` not on PATH in the agent/hook context, or a pre-existing turbo binary mismatch) but the local CI gate has already passed, use `--no-validate` for that merge only. Confirm the gate is clean first:
> ```bash
> bash .claude/hooks/run-ci-filtered.sh   # or: make toolbox-ci-all
> # If exit 0, proceed:
> bash .ctx/skills/branch-merge/scripts/safe-merge.sh <branch> --no-validate [--push]
> ```
> This is NOT a blanket skip — it means "I already validated; don't repeat it."

### Step 4: Execute Merge

Use the safe merge script. Accepts jj bookmarks, git branches, or commit/change IDs:

```bash
# Merge a bookmark/branch into main
bash .ctx/skills/branch-merge/scripts/safe-merge.sh <source-ref>

# Merge and push in one step
bash .ctx/skills/branch-merge/scripts/safe-merge.sh <source-ref> --push

# Skip pre-merge validation (use with caution)
bash .ctx/skills/branch-merge/scripts/safe-merge.sh <source-ref> --no-validate

# Agent/CI mode (auto-detected via CLAUDE_CODE or CI env vars, or explicit):
bash .ctx/skills/branch-merge/scripts/safe-merge.sh <source-ref> --yes [--push]

# Skip post-merge spec updates (if you want to handle them separately):
bash .ctx/skills/branch-merge/scripts/safe-merge.sh <source-ref> --no-spec-update

# Force interactive mode even when auto-detection says non-interactive:
bash .ctx/skills/branch-merge/scripts/safe-merge.sh <source-ref> --interactive
```

> **Agent mode**: Non-interactive mode is auto-detected when stdin is not a TTY, or `$CLAUDE_CODE` / `$CI` env vars are set. Use `--yes` (alias: `--non-interactive`) to force non-interactive mode. Use `--interactive` to override auto-detection and force prompts.

The script handles these scenarios automatically:

| Capability | Behavior |
|-----------|----------|
| CI gate | Runs full validation (unless `--no-validate`) — same as `ci.yml` |
| Auto-rebase on divergence | Rebases source onto main if not a direct descendant |
| Conflict detection | Halts with error if merge conflicts are detected |
| Backup tag (git mode) | Creates `tmp-*` tag before merge for rollback |
| Fast-forward fallback (git mode) | Attempts `--ff-only`, falls back to `--no-ff` |
| Stash pop graceful failure | Warns but doesn't abort if stash pop conflicts |
| `--non-interactive` auto-detect | Skips prompts when stdin is not a TTY, or `$CLAUDE_CODE`/`$CI` is set |
| `--interactive` override | Forces interactive mode even when auto-detection says non-interactive |
| `--yes` alias | Shorthand for `--non-interactive` |
| Post-merge spec updates | Automatically runs `post-merge-specs.sh` after merge (skip with `--no-spec-update`) |

### Step 5: Push and Cleanup

After merging, push and clean up. If you used `--push` in Step 4, skip the push command below.

```bash
# Push main to origin (if not already pushed via --push in Step 4)
# jj mode:
jj git push --bookmark main
# git mode:
git push origin main

# Dry run first to see what would be deleted
bash .ctx/skills/branch-merge/scripts/cleanup-merged.sh --dry-run

# Remove merged bookmarks/branches
bash .ctx/skills/branch-merge/scripts/cleanup-merged.sh
```

> **Squash-merge note**: `cleanup-merged.sh` uses `git branch --merged` which misses squash-merged
> branches. After running cleanup, verify with `git log --oneline main..<branch>` for any
> remaining branches — empty output means they are merged and can be safely deleted with `git branch -d`.

### Step 6: Post-Merge Spec & INDEX Updates

> **Automated**: `safe-merge.sh` now runs `post-merge-specs.sh` automatically after merge.
> Skip with `--no-spec-update` if you want manual control.

The post-merge spec update script handles:
1. Resolving branch name → spec file (via INDEX.md Branch column)
2. Verifying the branch is actually merged
3. Updating the spec's Status metadata to `**MERGED** (YYYY-MM-DD)`
4. Closing remaining workstreams in Implementation Checkpoint
5. Moving the spec to `specs/archive/`
6. Updating INDEX.md links (→ `archive/`) and status column
7. Updating Tier Overview summaries

**Manual usage** (if `--no-spec-update` was passed or script failed):
```bash
# Full automation:
bash .ctx/skills/branch-merge/scripts/post-merge-specs.sh <branch-name>

# Dry run first:
bash .ctx/skills/branch-merge/scripts/post-merge-specs.sh <branch-name> --dry-run

# Custom merge date:
bash .ctx/skills/branch-merge/scripts/post-merge-specs.sh <branch-name> --date 2026-03-17
```

**Verification** (after spec updates):
```bash
# Cross-validate consistency
bash .ctx/skills/update-specs/scripts/spec-lint.sh --verbose

# Check diff
git diff specs/
```

> **Cascade rule**: If all Task Registry items are `DONE`, the corresponding workstream MUST be
> `✅ DONE`. If all workstreams are `✅ DONE`, the Progress header should be `### Progress (Completed)`.

> **For mid-implementation updates** (not post-merge), use the `update-specs` skill with `spec-sync.sh`.

---

## Examples

### Example 1: Merge jj Bookmark into Main

```bash
# 1. Check status — see all bookmarks and their tracking
bash .ctx/skills/branch-merge/scripts/branch-status.sh

# 2. Merge the bookmark (jj squashes into main automatically)
bash .ctx/skills/branch-merge/scripts/safe-merge.sh feat/0.2.16-publisher-assembly-theme-config --push

# 3. Clean up merged bookmarks
bash .ctx/skills/branch-merge/scripts/cleanup-merged.sh
```

### Example 2: Merge Detached Change (jj orphan or git detached HEAD)

```bash
# 1. Check status — identifies orphaned changes
bash .ctx/skills/branch-merge/scripts/branch-status.sh

# 2. jj: use change ID; git: use commit SHA
bash .ctx/skills/branch-merge/scripts/safe-merge.sh qkplztyz --push
# or for git:
bash .ctx/skills/branch-merge/scripts/safe-merge.sh abc1234 --push
```

### Example 3: Merge Unbookmarked Stack Commits into Main

When commits sit above main without a bookmark (common after stacked jj work):

```bash
# 1. Check status — see stack commits above main
bash .ctx/skills/branch-merge/scripts/branch-status.sh

# 2. If stack is a direct descendant of main, advance the bookmark:
jj bookmark set main -r @-   # @- = last committed change (skip working copy)
jj git push --bookmark main

# 3. If stack diverges from main, rebase first:
jj rebase -s <first-stack-commit> -d main
# Resolve any conflicts, then advance:
jj bookmark set main -r @-
jj git push --bookmark main
```

### Example 4: Merge a Branch with an Open GitHub PR

When the source branch has an associated PR, prefer merging via GitHub to preserve PR metadata:

```bash
# 1. Check PR state
gh pr view <number> --json mergeable,mergeStateStatus

# 2a. If MERGEABLE — squash merge directly:
gh pr merge <number> --squash --delete-branch

# 2b. If CONFLICTING — rebase onto updated main first:
jj git fetch
git checkout <branch-name>
git rebase origin/main
# Resolve conflicts, then:
git push --force-with-lease origin <branch-name>
gh pr merge <number> --squash --delete-branch

# 3. Sync local after GitHub merge:
jj git fetch
```

### Example 6: Resolving rebase conflicts by keeping HEAD + re-applying biome

When rebasing produces conflicts in formatted files:
1. `git rebase origin/main` — resolve each conflict keeping HEAD (main) version
2. `make toolbox-lint-fix` — re-apply biome auto-format
3. `git add -A && git rebase --continue`
4. `git push --force-with-lease origin <branch>`

Biome formatting is deterministic — the format pass produces canonical output regardless of resolution.

### Example 5: Using the agentfs TypeScript API

```typescript
import { VigiaRuntime } from 'agentfs'

const runtime = new VigiaRuntime({ repoPath: '/path/to/repo' })

// Rebase a stacked change onto main
await runtime.rebaseStack({ destinationRevision: 'main' })

// Describe the merged change
await runtime.describeChange({ message: 'feat: merged feature X' })
```

---

## Verification

| Check | jj Command | git Command | Success Criteria |
|-------|------------|-------------|-----------------|
| Main synced | `jj git fetch && jj log -r 'main'` | `git log --oneline origin/main..main` | No divergence |
| No conflict markers | `grep -rn '<<<<<<' specs/ toolbox/` | Same | No matches |
| Clean working copy | `jj status` | `git status --short` | No unexpected changes |
| Bookmarks pushed | `jj bookmark list --all` | `git branch -vv` | All tracking in sync |
| Squash-merge detected | — | `git log --oneline main..<ref>` | Empty output for merged branches |
| Specs updated | Read spec files | Same | Status fields show CLOSED/DONE |
| INDEX.md updated | Read `specs/INDEX.md` | Same | PR rows show `Merged (YYYY-MM-DD)` |
| Spec consistency | `bash .ctx/skills/update-specs/scripts/spec-lint.sh` | Same | Exit 0, no FAIL results |
| Scripts executable | `ls -la .ctx/skills/branch-merge/scripts/` | Same | All `.sh` have `x` |
| Divergence analysis | `jj log --left-right -r 'origin/main...branch'` | `git log --left-right origin/main...branch --oneline` | Shows commits unique to each side |

---

## Troubleshooting

| Issue | Cause | Resolution |
|-------|-------|------------|
| Validation fails but CI already passed | `bun` not on PATH in agent/hook context, or pre-existing turbo mismatch | Run `make toolbox-ci-all` or `bash .claude/hooks/run-ci-filtered.sh` first; if exit 0, retry merge with `--no-validate` |
| `--ff-only` fails (git) | Main diverged from source | Rebase source: `jj rebase -r <src> -d main` or `git rebase main` |
| "Refusing to move bookmark backwards or sideways" (jj) | Source diverges from main — not a descendant | Rebase first: `jj rebase -s <root-of-source> -d main`, then retry `jj bookmark set` |
| PR shows CONFLICTING on GitHub | Main advanced past PR base, or bun.lock version skew | Rebase onto updated main + force-push. If still CONFLICTING with zero code conflicts: `git diff origin/main -- toolbox/bun.lock` — lockfile version skew triggers GitHub's own check. Sync: `git show origin/main:toolbox/bun.lock > toolbox/bun.lock && git commit -m 'fix: sync bun.lock with main'`. Or use `safe-merge.sh --sync-lockfile`. |
| Bookmark conflict (jj) | Bookmark moved on remote | `jj git fetch` then `jj bookmark set main -r <target>` |
| Stash pop conflicts (git) | Merge changed same files | Resolve manually; stash is preserved |
| Pre-commit hook fails | codeveritas finds issues | Fix violations, re-stage, commit |
| Push rejected | Remote has new commits | `jj git fetch && jj rebase -d main@origin` or `git pull --rebase` |
| jj binary not found | Not installed or not in PATH | Install via `cargo install jj-cli` or fall back to git mode |
| `git rebase --continue` fails "edit all merge conflicts" but `git ls-files -u` is empty | jj created `.git/AUTO_MERGE` sentinel files | `rm -f .git/AUTO_MERGE '.git/AUTO_MERGE 2' ... '.git/AUTO_MERGE 9'` then retry |
| CI blocked by GitHub billing/quota | GitHub Actions quota exhausted | `gh pr merge <N> --squash --admin` (only when `make toolbox-ci-all` exits 0 locally) |
| Rebase hits squash-merged commit | Phantom conflict from already-squashed change | `git rebase --skip` (drops the phantom conflict) |

---

## Anti-Patterns

| Don't | Do Instead |
|-------|------------|
| `git push --force origin main` | Normal push; rebase if rejected |
| `git reset --hard` without backup | jj snapshots automatically; use `jj undo` |
| Skip pre-merge validation | At minimum run `--quick` validation |
| Merge with dirty tree (git) | Stash first, or let jj handle it |
| Delete bookmarks without checking | Use `--dry-run` first |
| Use `--no-verify` on commits | Fix the pre-commit hook issue |
| Mix jj and git commands carelessly | Use one VCS per operation; scripts handle this |
| Merge without updating specs | Run Step 6 after every merge to keep specs in sync |
| Rely on `git branch --merged` alone | Use `git log --oneline main..<ref>` to catch squash-merges |

---

## Integration with agentfs

The `agentfs` package (`toolbox/packages/agentfs/`) provides typed jj operations:

| agentfs API | Shell Script Equivalent |
|-------------|------------------------|
| `probeJjBinary()` | `command -v jj` |
| `probeJjRepository()` | `test -d .jj` |
| `executeJujutsuOperation({ type: 'bookmark_list' })` | `jj bookmark list` |
| `VigiaRuntime.rebaseStack()` | `jj rebase -r <src> -d main` |
| `VigiaRuntime.describeChange()` | `jj describe -m "..."` |

For programmatic workflows (CI, agents), prefer the TypeScript API. For interactive/CLI workflows, use these shell scripts.
