#!/usr/bin/env bash
set -euo pipefail

# create-pr-branch.sh — VCS-aware branch/bookmark creation with optional worktree
#
# Usage: create-pr-branch.sh <branch-name> [--worktree] [--from <revision>] [--json]
#
# Creates a jj bookmark (preferred) or git branch from a base revision.
# Optionally creates an isolated worktree for parallel PR work.
#
# Exit codes:
#   0  Branch/bookmark created successfully
#   1  Error (details printed)

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# ── Parse arguments ───────────────────────────────────────
BRANCH_NAME=""
WORKTREE=false
FROM_REV="main"
JSON_OUTPUT=false

show_help() {
  cat <<'USAGE'
Usage: create-pr-branch.sh <branch-name> [--worktree] [--from <revision>] [--json]

Arguments:
  <branch-name>       Name for the new branch/bookmark (e.g. feat/0.2.25-feature)

Options:
  --worktree          Create an isolated worktree (jj workspace or git worktree)
  --from <revision>   Base revision (default: main)
  --json              Output result as JSON
  --help              Show this help

Examples:
  create-pr-branch.sh feat/0.2.25-todo-cleanup
  create-pr-branch.sh feat/0.2.26-svg-export --worktree --from main
  create-pr-branch.sh feat/0.2.27-vigia --json
USAGE
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h) show_help ;;
    --worktree) WORKTREE=true; shift ;;
    --from) FROM_REV="$2"; shift 2 ;;
    --json) JSON_OUTPUT=true; shift ;;
    -*) echo "Unknown option: $1"; exit 1 ;;
    *) BRANCH_NAME="$1"; shift ;;
  esac
done

if [ -z "$BRANCH_NAME" ]; then
  echo "Error: branch name is required"
  echo "Run with --help for usage"
  exit 1
fi

# ── Detect VCS backend ────────────────────────────────────
JJ_AVAILABLE=false
if command -v jj &>/dev/null && [ -d ".jj" ]; then
  JJ_AVAILABLE=true
fi

VCS="git"
WORKTREE_PATH=""

# ── Create branch ─────────────────────────────────────────
if [ "$JJ_AVAILABLE" = true ]; then
  VCS="jj"

  if [ "$WORKTREE" = true ]; then
    # Create isolated jj workspace
    WORKTREE_PATH="../pr-workspace-${BRANCH_NAME//\//-}"
    echo "Creating jj workspace at $WORKTREE_PATH..."
    jj workspace add "$WORKTREE_PATH" --revision "$FROM_REV"
    cd "$WORKTREE_PATH"
    jj bookmark create "$BRANCH_NAME" -r @
    echo "Workspace created at: $WORKTREE_PATH"
    echo "Bookmark created: $BRANCH_NAME"
  else
    # Direct creation in current workspace
    echo "Creating new change from $FROM_REV..."
    jj new "$FROM_REV" -m "feat: start $BRANCH_NAME"
    jj bookmark create "$BRANCH_NAME" -r @
    echo "Bookmark created: $BRANCH_NAME"
  fi

else
  # ── Git fallback ──────────────────────────────────────
  VCS="git"

  if [ "$WORKTREE" = true ]; then
    # Create git worktree
    WORKTREE_PATH="../pr-workspace-${BRANCH_NAME//\//-}"
    echo "Creating git worktree at $WORKTREE_PATH..."
    git worktree add -b "$BRANCH_NAME" "$WORKTREE_PATH" "$FROM_REV"
    echo "Worktree created at: $WORKTREE_PATH"
    echo "Branch created: $BRANCH_NAME"
  else
    # Direct branch creation
    echo "Creating branch from $FROM_REV..."
    git checkout -b "$BRANCH_NAME" "$FROM_REV"
    echo "Branch created: $BRANCH_NAME"
  fi
fi

# ── Output ────────────────────────────────────────────────
if [ "$JSON_OUTPUT" = true ]; then
  WORKTREE_RESOLVED=""
  if [ -n "$WORKTREE_PATH" ]; then
    WORKTREE_RESOLVED="$(realpath "$WORKTREE_PATH" 2>/dev/null || echo "$WORKTREE_PATH")"
  fi
  # Use jq for safe JSON construction (handles special characters in branch names)
  jq -n \
    --arg branch "$BRANCH_NAME" \
    --arg worktree "$WORKTREE_RESOLVED" \
    --arg vcs "$VCS" \
    --arg from "$FROM_REV" \
    '{branch: $branch, worktree: (if $worktree == "" then null else $worktree end), vcs: $vcs, from: $from}'
fi

echo ""
echo "Branch ready: $BRANCH_NAME (via $VCS)"
