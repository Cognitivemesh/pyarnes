#!/usr/bin/env bash
set -euo pipefail

# safe-merge.sh — Safely merge a ref/bookmark into main (jj-native with git fallback)
# Usage: safe-merge.sh <source-ref> [--push] [--no-validate]
#
# Pre-merge validation runs the full CI gate by default (install → build → check → typecheck → tests).
# Use --no-validate only if you already ran pre-merge-validate.sh manually.
#
# In jj mode:
#   - Auto-rebases diverged branches onto main before advancing
#   - Uses jj bookmark operations to advance main
#   - Pushes via jj git push
#   - Working copy is automatically snapshotted (no stash needed)
#
# In git mode:
#   - Auto-stashes dirty tree
#   - Creates backup tag
#   - Attempts --ff-only, falls back to --no-ff
#   - Restores stash after merge

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=lib/jj-rebase-guard.sh
source "$SCRIPT_DIR/lib/jj-rebase-guard.sh" 2>/dev/null || true

# Detect VCS backend
JJ_AVAILABLE=false
if command -v jj &>/dev/null && [ -d ".jj" ]; then
  JJ_AVAILABLE=true
fi

# Parse arguments
SOURCE_REF=""
DO_PUSH=false
DO_VALIDATE=true

NON_INTERACTIVE=false
FORCE_INTERACTIVE=false
DO_SPEC_UPDATE=true

for arg in "$@"; do
  case "$arg" in
    --push) DO_PUSH=true ;;
    --no-validate) DO_VALIDATE=false ;;
    --non-interactive|--yes) NON_INTERACTIVE=true ;;
    --interactive) FORCE_INTERACTIVE=true ;;
    --no-spec-update) DO_SPEC_UPDATE=false ;;
    --sync-lockfile) ;; # handled in bun.lock divergence check below
    -*) echo "Unknown option: $arg"; exit 1 ;;
    *) SOURCE_REF="$arg" ;;
  esac
done

# Auto-detect non-interactive mode (agent/CI):
# - --interactive explicitly overrides auto-detection
# - stdin is not a TTY (piped, redirected, or agent context)
# - CLAUDE_CODE is set (Claude Code agent environment)
# - CI is set (CI/CD pipeline)
if [ "$FORCE_INTERACTIVE" = true ]; then
  NON_INTERACTIVE=false
elif [ ! -t 0 ] || [ -n "${CLAUDE_CODE:-}" ] || [ -n "${CI:-}" ]; then
  NON_INTERACTIVE=true
fi

if [ -z "$SOURCE_REF" ]; then
  echo "Usage: safe-merge.sh <source-ref> [--push] [--no-validate] [--no-spec-update] [--sync-lockfile]"
  echo ""
  echo "  source-ref        jj bookmark, jj change ID, git branch, or commit SHA"
  echo "  --push            Push main to origin after merge"
  echo "  --no-validate     Skip pre-merge CI validation"
  echo "  --yes             Auto-confirm merge commits (alias: --non-interactive)"
  echo "  --interactive     Force interactive mode (overrides TTY auto-detection)"
  echo "  --no-spec-update  Skip post-merge spec updates"
  echo "  --sync-lockfile   Auto-sync toolbox/bun.lock from origin/main before merge"
  echo ""
  if [ "$JJ_AVAILABLE" = true ]; then
    echo "VCS: jujutsu + git (jj-native mode)"
  else
    echo "VCS: git only"
  fi
  exit 1
fi

# Stash hygiene pre-check: warn about stale stashes for the source branch
STASH_COUNT="$(git stash list 2>/dev/null | grep -c "$SOURCE_REF" || true)"
if [ "$STASH_COUNT" -gt 0 ]; then
  echo ""
  echo "WARNING: $STASH_COUNT stash(es) found referencing '$SOURCE_REF'"
  echo "  Review with: git stash list | grep '$SOURCE_REF'"
  echo "  Stale stashes from prior sessions can cause conflicts after merge."
  echo "  Consider dropping them before proceeding: git stash drop <stash-ref>"
  echo ""
fi

# bun.lock divergence check
LOCK_DIFF="$(git diff "origin/main" -- toolbox/bun.lock 2>/dev/null)"
if [ -n "$LOCK_DIFF" ]; then
  echo ""
  echo "WARNING: toolbox/bun.lock diverges from origin/main."
  echo "  GitHub may report CONFLICTING even after a clean rebase."
  echo "  To sync: git show origin/main:toolbox/bun.lock > toolbox/bun.lock"
  echo "           git add toolbox/bun.lock && git commit -m 'fix: sync bun.lock with main'"
  echo "  Or pass --sync-lockfile to this script to sync automatically."
  if [[ " $* " =~ " --sync-lockfile " ]]; then
    echo "  Auto-syncing bun.lock from origin/main..."
    git show origin/main:toolbox/bun.lock > toolbox/bun.lock
    git add toolbox/bun.lock
    git commit -m "fix: sync bun.lock with main before merge"
  fi
fi

# Pre-merge validation
if [ "$DO_VALIDATE" = true ]; then
  echo ""
  echo "Running pre-merge validation..."
  VALIDATE_EXIT=0
  bash "$SCRIPT_DIR/pre-merge-validate.sh" || VALIDATE_EXIT=$?

  case "$VALIDATE_EXIT" in
    0) ;; # All checks passed
    2)
      echo ""
      echo "WARNING: Tests passed but coverage threshold missed."
      echo "Proceeding with merge (coverage-only failure is non-blocking)."
      ;;
    3)
      echo ""
      echo "ERROR: Lint/format issues detected. Run 'make toolbox-lint-fix' and retry."
      exit 1
      ;;
    *)
      echo ""
      echo "ERROR: Pre-merge validation failed. Fix issues before merging."
      exit 1
      ;;
  esac
fi

if [ "$JJ_AVAILABLE" = true ]; then
  # ═══════════════════════════════════════════════════════════
  # jj-native merge
  # ═══════════════════════════════════════════════════════════

  echo ""
  echo "VCS: jujutsu mode"
  echo "Source: $SOURCE_REF"

  # Snapshot current state
  jj status --no-pager &>/dev/null  # triggers auto-snapshot

  # Check if source is a bookmark
  IS_BOOKMARK=false
  if jj bookmark list --no-pager 2>/dev/null | grep -q "^${SOURCE_REF}:"; then
    IS_BOOKMARK=true
    echo "Detected as jj bookmark"
  fi

  # Resolve the source to a commit
  # --no-graph suppresses tree decorations so the template output is captured cleanly
  SOURCE_COMMIT="$(jj log --no-pager --no-graph -r "$SOURCE_REF" --limit 1 -T 'commit_id.short(12)' 2>/dev/null || true)"
  if [ -z "$SOURCE_COMMIT" ]; then
    # Try as a git ref
    SOURCE_COMMIT="$(git rev-parse --short "$SOURCE_REF" 2>/dev/null || true)"
  fi

  if [ -z "$SOURCE_COMMIT" ]; then
    echo "ERROR: Cannot resolve '$SOURCE_REF' as jj change or git ref"
    exit 1
  fi

  MAIN_BEFORE="$(jj log --no-pager --no-graph -r 'main' --limit 1 -T 'commit_id.short(12)' 2>/dev/null)"
  echo "main before: $MAIN_BEFORE"
  echo "source:      $SOURCE_COMMIT"

  # Check if source is a descendant of main (forward move) or diverged (needs rebase)
  IS_DESCENDANT=false
  if jj log --no-pager --no-graph -r "ancestors($SOURCE_REF) & main" --limit 1 -T 'commit_id.short(12)' 2>/dev/null | grep -q .; then
    # main is in the ancestry of source — forward move is safe
    IS_DESCENDANT=true
  fi

  # Move main bookmark to include the source
  echo ""
  if [ "$IS_DESCENDANT" = true ]; then
    echo "Advancing main bookmark to $SOURCE_REF (forward move)..."
    jj bookmark set main -r "$SOURCE_REF" --no-pager 2>/dev/null
  else
    echo "Source diverges from main — attempting rebase first..."
    # Find the root of the source branch (first commit not in main)
    SOURCE_ROOT="$(jj log --no-pager --no-graph -r "roots(ancestors($SOURCE_REF) ~ ancestors(main))" --limit 1 -T 'change_id.short(12)' 2>/dev/null || true)"
    REBASE_OK=false
    if [ -n "$SOURCE_ROOT" ]; then
      REBASE_OUT="$(jj rebase -s "$SOURCE_ROOT" -d main --no-pager 2>&1)"
      REBASE_EXIT=$?
      if [ "$REBASE_EXIT" -eq 0 ]; then
        REBASE_OK=true
        RESOLVE_OUT="$(jj resolve --list -r "$SOURCE_REF" --no-pager 2>/dev/null)"
        if echo "$RESOLVE_OUT" | grep -q 'conflict'; then
          echo ""
          echo "ERROR: Rebase produced conflicts. Resolve manually:"
          echo "$RESOLVE_OUT"
          exit 1
        fi
        echo "Advancing main bookmark to rebased $SOURCE_REF..."
        jj bookmark set main -r "$SOURCE_REF" --no-pager 2>/dev/null
      else
        echo "$REBASE_OUT"
      fi
    fi

    if [ "$REBASE_OK" = false ]; then
      # Source commits are immutable (already pushed to remote) — cannot rebase.
      # Create a jj merge commit with both main and source as parents instead.
      echo "Immutable commits detected — creating merge commit (jj new main $SOURCE_REF)..."
      jj new main "$SOURCE_REF" --no-pager
      RESOLVE_OUT="$(jj resolve --list -r "@" --no-pager 2>/dev/null)"
      if echo "$RESOLVE_OUT" | grep -q 'conflict'; then
        echo ""
        echo "ERROR: Merge produced conflicts. Resolve manually then run:"
        echo "  jj describe -m 'merge: $SOURCE_REF into main'"
        echo "  jj bookmark set main -r @"
        echo "$RESOLVE_OUT"
        exit 1
      fi
      jj describe -m "merge: $SOURCE_REF into main" --no-pager 2>/dev/null
      jj bookmark set main -r "@" --no-pager 2>/dev/null
    fi
  fi

  MAIN_AFTER="$(jj log --no-pager --no-graph -r 'main' --limit 1 -T 'commit_id.short(12)' 2>/dev/null)"
  echo "main after:  $MAIN_AFTER"

  # Push via jj git push
  if [ "$DO_PUSH" = true ]; then
    echo ""
    echo "Pushing main to origin via jj..."
    if jj git push --bookmark main --no-pager 2>/dev/null; then
      echo "Push successful."
    else
      echo "WARNING: jj git push failed. Falling back to git push..."
      git push origin main || echo "ERROR: Push failed."
    fi
  fi

  # Clean up: if source was a bookmark and it's now at main, optionally delete it
  if [ "$IS_BOOKMARK" = true ] && [ "$SOURCE_REF" != "main" ]; then
    echo ""
    echo "Note: Bookmark '$SOURCE_REF' still exists. Run cleanup to remove merged bookmarks."
  fi

else
  # ═══════════════════════════════════════════════════════════
  # git-only merge
  # ═══════════════════════════════════════════════════════════

  echo ""
  echo "VCS: git-only mode"

  # Verify source ref
  if ! git rev-parse --verify "$SOURCE_REF" &>/dev/null; then
    echo "ERROR: ref '$SOURCE_REF' does not exist"
    exit 1
  fi

  SOURCE_SHA="$(git rev-parse --short "$SOURCE_REF")"
  MAIN_SHA="$(git rev-parse --short main)"
  echo "Source: $SOURCE_REF ($SOURCE_SHA)"
  echo "Target: main ($MAIN_SHA)"

  # Already merged?
  if [ "$(git rev-parse main)" = "$(git rev-parse "$SOURCE_REF")" ]; then
    echo "Nothing to merge — main is already at $SOURCE_SHA"
    exit 0
  fi

  # Stash if dirty
  STASHED=false
  if [ -n "$(git status --porcelain)" ]; then
    STASH_MSG="wip: auto-stash before merge of $SOURCE_REF ($(date +%Y%m%d-%H%M%S))"
    echo ""
    echo "Working tree is dirty — stashing..."
    git stash push -m "$STASH_MSG"
    STASHED=true
  fi

  # Backup tag
  BACKUP_TAG="tmp-pre-merge-$(date +%s)"
  git tag "$BACKUP_TAG" main

  # Switch to main
  ORIGINAL_REF="$(git symbolic-ref --short HEAD 2>/dev/null || git rev-parse --short HEAD)"
  git checkout main 2>/dev/null

  # Fast-forward merge
  echo ""
  echo "Attempting fast-forward merge..."
  if git merge --ff-only "$SOURCE_REF" 2>/dev/null; then
    echo "Fast-forward merge successful: $MAIN_SHA → $(git rev-parse --short HEAD)"
  else
    echo "Fast-forward not possible."
    if [ "$NON_INTERACTIVE" = true ]; then
      echo "Non-interactive mode: creating merge commit automatically."
      git merge --no-ff "$SOURCE_REF" -m "merge: $SOURCE_REF into main"
      echo "Merge commit created: $(git rev-parse --short HEAD)"
    else
      read -rp "Create a merge commit instead? [y/N] " confirm
      if [[ "$confirm" =~ ^[Yy]$ ]]; then
        git merge --no-ff "$SOURCE_REF" -m "Merge $SOURCE_REF into main"
        echo "Merge commit created: $(git rev-parse --short HEAD)"
      else
        echo "Merge aborted."
        git checkout "$ORIGINAL_REF" 2>/dev/null || true
        git tag -d "$BACKUP_TAG" 2>/dev/null
        [ "$STASHED" = true ] && git stash pop
        exit 1
      fi
    fi
  fi

  # Push
  if [ "$DO_PUSH" = true ]; then
    echo ""
    echo "Pushing to origin/main..."
    git push origin main || echo "WARNING: Push failed."
  fi

  # Restore stash
  if [ "$STASHED" = true ]; then
    echo ""
    echo "Restoring stashed changes..."
    git stash pop || echo "WARNING: Stash pop had conflicts. Stash preserved."
  fi

  # Cleanup backup
  git tag -d "$BACKUP_TAG" &>/dev/null
fi

# Post-merge spec updates
if [ "$DO_SPEC_UPDATE" = true ]; then
  POST_MERGE_SCRIPT="$SCRIPT_DIR/post-merge-specs.sh"
  if [ -x "$POST_MERGE_SCRIPT" ]; then
    echo ""
    echo "Running post-merge spec updates..."
    POST_MERGE_EXIT=0
    bash "$POST_MERGE_SCRIPT" "$SOURCE_REF" || POST_MERGE_EXIT=$?
    if [ "$POST_MERGE_EXIT" -eq 0 ]; then
      echo "Spec updates complete."
    else
      echo "WARNING: Post-merge spec update failed (exit $POST_MERGE_EXIT, non-fatal). Run manually:"
      echo "  bash $POST_MERGE_SCRIPT $SOURCE_REF"
    fi
  fi
fi

# Summary
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  Merge Summary"
echo "═══════════════════════════════════════════════════════════"
echo "  Source:  $SOURCE_REF"
if [ "$JJ_AVAILABLE" = true ]; then
  echo "  Mode:    jujutsu"
  echo "  main:    $(jj log --no-pager --no-graph -r 'main' --limit 1 -T 'commit_id.short(12)' 2>/dev/null)"
else
  echo "  Mode:    git"
  echo "  main:    $(git rev-parse --short main)"
fi
if [ "$DO_PUSH" = true ]; then
  echo "  Pushed:  yes"
fi
echo "═══════════════════════════════════════════════════════════"
