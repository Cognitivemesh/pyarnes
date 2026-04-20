#!/usr/bin/env bash
set -uo pipefail

# branch-status.sh — Show branch/bookmark state (jj-native with git fallback)
# Usage: bash .ctx/skills/branch-merge/scripts/branch-status.sh

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# Detect VCS backend
JJ_AVAILABLE=false
if command -v jj &>/dev/null && [ -d ".jj" ]; then
  JJ_AVAILABLE=true
fi

echo "═══════════════════════════════════════════════════════════"
echo "  Branch Status Report"
if [ "$JJ_AVAILABLE" = true ]; then
  echo "  VCS: jujutsu $(jj version 2>/dev/null | head -1) + git"
else
  echo "  VCS: git only"
fi
echo "═══════════════════════════════════════════════════════════"
echo ""

if [ "$JJ_AVAILABLE" = true ]; then
  # ── jj mode ──────────────────────────────────────────────

  # Current working copy change
  echo "Working copy:"
  jj log --no-pager -r '@' --limit 1 2>/dev/null || echo "  (unable to read)"
  echo ""

  # Bookmarks (jj's branches)
  echo "Bookmarks:"
  echo "───────────────────────────────────────────────────────────"
  jj bookmark list --all --no-pager 2>/dev/null | while IFS= read -r line; do
    echo "  $line"
  done
  echo ""

  # Changes above main (stacked work)
  ABOVE_MAIN="$(jj log --no-pager -r 'main..@' --limit 20 2>/dev/null || true)"
  if [ -n "$ABOVE_MAIN" ]; then
    echo "Changes above main:"
    echo "───────────────────────────────────────────────────────────"
    echo "$ABOVE_MAIN"
    echo ""
  fi

  # Working copy status
  echo "Working copy status:"
  jj status --no-pager 2>/dev/null | head -20
  echo ""

  # Git sync status (main vs origin/main)
  echo "Git sync:"
  echo "───────────────────────────────────────────────────────────"
  if git rev-parse --verify origin/main &>/dev/null; then
    MAIN_SHA="$(git rev-parse --short main 2>/dev/null || echo 'N/A')"
    ORIGIN_SHA="$(git rev-parse --short origin/main 2>/dev/null || echo 'N/A')"
    COUNTS="$(git rev-list --left-right --count origin/main...main 2>/dev/null || echo '0	0')"
    BEHIND="$(echo "$COUNTS" | cut -f1)"
    AHEAD="$(echo "$COUNTS" | cut -f2)"
    echo "  main:        $MAIN_SHA"
    echo "  origin/main: $ORIGIN_SHA (main is ${AHEAD} ahead, ${BEHIND} behind)"
  else
    echo "  origin/main: not found"
  fi

else
  # ── git-only mode ────────────────────────────────────────

  # HEAD state
  if git symbolic-ref HEAD &>/dev/null; then
    BRANCH="$(git symbolic-ref --short HEAD)"
    echo "HEAD:     on branch '$BRANCH' at $(git rev-parse --short HEAD)"
  else
    echo "HEAD:     DETACHED at $(git rev-parse --short HEAD)"
  fi
  echo ""

  # Main vs origin/main
  if git rev-parse --verify main &>/dev/null; then
    MAIN_SHA="$(git rev-parse --short main)"
    echo "main:     $MAIN_SHA"

    if git rev-parse --verify origin/main &>/dev/null; then
      ORIGIN_SHA="$(git rev-parse --short origin/main)"
      COUNTS="$(git rev-list --left-right --count origin/main...main 2>/dev/null || echo '0	0')"
      BEHIND="$(echo "$COUNTS" | cut -f1)"
      AHEAD="$(echo "$COUNTS" | cut -f2)"
      echo "origin:   $ORIGIN_SHA (main is ${AHEAD} ahead, ${BEHIND} behind)"
    fi
  fi
  echo ""

  # Commits ahead of main
  CURRENT="$(git symbolic-ref --short HEAD 2>/dev/null || echo HEAD)"
  if [ "$CURRENT" != "main" ] && git rev-parse --verify main &>/dev/null; then
    AHEAD_COUNT="$(git rev-list --count main.."$CURRENT" 2>/dev/null || echo 0)"
    if [ "$AHEAD_COUNT" -gt 0 ]; then
      echo "Commits ahead of main ($AHEAD_COUNT):"
      git log --oneline main.."$CURRENT"
      echo ""
    fi
  fi

  # All local branches
  echo "Local branches:"
  echo "───────────────────────────────────────────────────────────"
  git branch -vv --no-color 2>/dev/null | while IFS= read -r line; do
    echo "  $line"
  done
fi

echo ""

# Common stats (both modes)
STASH_COUNT="$(git stash list 2>/dev/null | wc -l | tr -d ' ')"
echo "Git stashes:   $STASH_COUNT"

echo ""
echo "═══════════════════════════════════════════════════════════"
