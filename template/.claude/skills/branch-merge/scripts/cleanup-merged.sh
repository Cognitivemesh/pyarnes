#!/usr/bin/env bash
set -euo pipefail

# cleanup-merged.sh — Remove merged bookmarks/branches (jj-native with git fallback)
# Usage: cleanup-merged.sh [--dry-run] [--include-remote]

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

DRY_RUN=false
INCLUDE_REMOTE=false

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --include-remote) INCLUDE_REMOTE=true ;;
    *) echo "Unknown option: $arg"; exit 1 ;;
  esac
done

# Detect VCS backend
JJ_AVAILABLE=false
if command -v jj &>/dev/null && [ -d ".jj" ]; then
  JJ_AVAILABLE=true
fi

echo "═══════════════════════════════════════════════════════════"
echo "  Cleanup Merged Bookmarks/Branches"
if [ "$DRY_RUN" = true ]; then
  echo "  (DRY RUN — no deletions)"
fi
if [ "$JJ_AVAILABLE" = true ]; then
  echo "  VCS: jujutsu + git"
else
  echo "  VCS: git only"
fi
echo "═══════════════════════════════════════════════════════════"
echo ""

DELETED=0

if [ "$JJ_AVAILABLE" = true ]; then
  # ── jj mode: check bookmarks that point to ancestors of main ──

  MAIN_REV="$(jj log --no-pager -r 'main' --limit 1 -T 'change_id.short(12)' 2>/dev/null)"
  echo "main at: $MAIN_REV"
  echo ""

  # List all bookmarks (use process substitution to avoid subshell counter bug)
  echo "Checking bookmarks..."
  while IFS= read -r line; do
    # Extract bookmark name (first word before ':')
    BMARK="$(echo "$line" | cut -d':' -f1 | tr -d ' ')"
    [ -z "$BMARK" ] && continue
    [ "$BMARK" = "main" ] && continue

    # Check if bookmark is an ancestor of main
    IS_ANCESTOR="$(jj log --no-pager -r "$BMARK & ancestors(main)" --limit 1 -T 'change_id.short(8)' 2>/dev/null || true)"

    if [ -n "$IS_ANCESTOR" ]; then
      if [ "$DRY_RUN" = true ]; then
        echo "  [dry-run] Would delete bookmark: $BMARK (merged into main)"
      else
        echo "  Deleting bookmark: $BMARK"
        jj bookmark delete "$BMARK" --no-pager 2>/dev/null || echo "    WARNING: Could not delete $BMARK"
      fi
      DELETED=$((DELETED + 1))
    else
      echo "  Keeping bookmark: $BMARK (not merged)"
    fi
  done < <(jj bookmark list --no-pager 2>/dev/null)

else
  # ── git mode: check branches merged into main ──

  CURRENT="$(git symbolic-ref --short HEAD 2>/dev/null || echo 'DETACHED')"
  if [ "$CURRENT" != "main" ]; then
    echo "Switching to main..."
    git checkout main 2>/dev/null
  fi

  MERGED_BRANCHES="$(git branch --merged main --no-color | grep -v '^\*' | grep -v 'main' | sed 's/^[[:space:]]*//' || true)"

  if [ -z "$MERGED_BRANCHES" ]; then
    echo "  No merged branches to clean up."
  else
    echo "Merged branches:"
    while IFS= read -r branch; do
      [ -z "$branch" ] && continue
      if [ "$DRY_RUN" = true ]; then
        echo "  [dry-run] Would delete: $branch"
      else
        echo "  Deleting: $branch"
        git branch -d "$branch" 2>/dev/null || echo "    WARNING: Could not delete $branch"
      fi
      DELETED=$((DELETED + 1))
    done <<< "$MERGED_BRANCHES"
  fi
fi

# Prune remote tracking refs
if [ "$INCLUDE_REMOTE" = true ]; then
  echo ""
  echo "Pruning remote tracking references..."
  if [ "$DRY_RUN" = true ]; then
    git remote prune origin --dry-run 2>/dev/null || true
  else
    git remote prune origin 2>/dev/null || true
  fi
fi

# Clean up old tmp-* backup tags
echo ""
OLD_TAGS="$(git tag -l 'tmp-*' 2>/dev/null || true)"
TAG_DELETED=0
if [ -n "$OLD_TAGS" ]; then
  echo "Checking tmp-* backup tags..."
  while IFS= read -r tag; do
    [ -z "$tag" ] && continue
    if [ "$DRY_RUN" = true ]; then
      echo "  [dry-run] Would delete tag: $tag"
    else
      echo "  Deleting tag: $tag"
      git tag -d "$tag" 2>/dev/null || true
    fi
    TAG_DELETED=$((TAG_DELETED + 1))
  done <<< "$OLD_TAGS"
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  Summary: $DELETED bookmarks/branches, $TAG_DELETED tags processed"
echo "═══════════════════════════════════════════════════════════"
