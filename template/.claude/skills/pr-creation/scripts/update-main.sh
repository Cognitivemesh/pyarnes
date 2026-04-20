#!/usr/bin/env bash
set -euo pipefail

# update-main.sh — Merge main (or specified base) into open PR branches
# Part of the pr-creation skill

# shellcheck source=../../branch-merge/scripts/lib/jj-rebase-guard.sh
source "$(git rev-parse --show-toplevel 2>/dev/null || echo .)/.ctx/skills/branch-merge/scripts/lib/jj-rebase-guard.sh" 2>/dev/null || true

show_help() {
  cat <<'USAGE'
Usage: update-main.sh [options]

Merge the base branch (default: main) into open PR branches to keep
them up to date. Skips branches with merge conflicts and reports them.

Options:
  --branch <name>    Target a single branch (instead of all open PRs)
  --base <name>      Base branch to merge from (default: main)
  --push             Push updated branches to origin
  --dry-run          List branches that would be updated
  --json             Output as JSON
  --help             Show this help

Examples:
  update-main.sh                             # Update all open PR branches
  update-main.sh --branch feat/my-feature    # Update one branch
  update-main.sh --push                      # Update and push
  update-main.sh --dry-run                   # Preview only
USAGE
  exit 0
}

TARGET_BRANCH=""
BASE="main"
PUSH=false
DRY_RUN=false
JSON_OUTPUT=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help) show_help ;;
    --branch) TARGET_BRANCH="$2"; shift 2 ;;
    --base) BASE="$2"; shift 2 ;;
    --push) PUSH=true; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    --json) JSON_OUTPUT=true; shift ;;
    -*) echo "Unknown option: $1" >&2; exit 1 ;;
    *) echo "Unexpected argument: $1" >&2; exit 1 ;;
  esac
done

# Check gh auth
if ! gh auth status &>/dev/null; then
  echo "Error: Not authenticated with GitHub CLI. Run 'gh auth login'." >&2
  exit 1
fi

# Remember current branch to restore later
ORIGINAL_BRANCH=$(git branch --show-current 2>/dev/null || git rev-parse --short HEAD)

# Fetch latest
git fetch origin "$BASE" 2>/dev/null

# Collect target branches
BRANCHES=()
if [[ -n "$TARGET_BRANCH" ]]; then
  BRANCHES=("$TARGET_BRANCH")
else
  while IFS= read -r b; do
    [[ -n "$b" ]] && BRANCHES+=("$b")
  done < <(gh pr list --state open --json headRefName --jq '.[].headRefName')
fi

if [[ ${#BRANCHES[@]} -eq 0 ]]; then
  echo "No branches to update."
  exit 0
fi

echo "Updating ${#BRANCHES[@]} branch(es) with origin/$BASE"
echo "────────────────────────────────────"

if [[ "$DRY_RUN" == true ]]; then
  for branch in "${BRANCHES[@]}"; do
    # Check if branch is behind base
    BEHIND=$(git rev-list --count "origin/${branch}..origin/${BASE}" 2>/dev/null || echo "?")
    echo "  $branch — $BEHIND commit(s) behind $BASE"
  done
  if [[ "$JSON_OUTPUT" == true ]]; then
    printf '%s\n' "${BRANCHES[@]}" | jq -R . | jq -s '{branches: ., dry_run: true}'
  fi
  exit 0
fi

UPDATED=()
CONFLICTS=()
SKIPPED=()

for branch in "${BRANCHES[@]}"; do
  echo ""
  echo "Updating: $branch"

  # Fetch the branch
  if ! git fetch origin "$branch" 2>/dev/null; then
    echo "  SKIP: Could not fetch origin/$branch"
    SKIPPED+=("$branch")
    continue
  fi

  # Check out the branch
  if ! git checkout "$branch" 2>/dev/null; then
    echo "  SKIP: Could not checkout $branch"
    SKIPPED+=("$branch")
    continue
  fi

  # Attempt merge
  if git merge "origin/$BASE" --no-edit 2>/dev/null; then
    echo "  Merged origin/$BASE into $branch"

    if [[ "$PUSH" == true ]]; then
      if git push origin "$branch" 2>/dev/null; then
        echo "  Pushed to origin/$branch"
      else
        echo "  WARNING: Push failed for $branch" >&2
      fi
    fi

    UPDATED+=("$branch")
  else
    echo "  CONFLICT: Merge conflict on $branch — aborting"
    git merge --abort 2>/dev/null || true
    CONFLICTS+=("$branch")
  fi
done

# Restore original branch
git checkout "$ORIGINAL_BRANCH" 2>/dev/null || true

echo ""
echo "────────────────────────────────────"
echo "Updated: ${#UPDATED[@]}  Conflicts: ${#CONFLICTS[@]}  Skipped: ${#SKIPPED[@]}"

if [[ ${#CONFLICTS[@]} -gt 0 ]]; then
  echo ""
  echo "Branches with conflicts (resolve manually):"
  printf '  - %s\n' "${CONFLICTS[@]}"
fi

if [[ "$JSON_OUTPUT" == true ]]; then
  jq -n \
    --argjson updated "$(printf '%s\n' "${UPDATED[@]:-}" | jq -R 'select(length > 0)' | jq -s '.')" \
    --argjson conflicts "$(printf '%s\n' "${CONFLICTS[@]:-}" | jq -R 'select(length > 0)' | jq -s '.')" \
    --argjson skipped "$(printf '%s\n' "${SKIPPED[@]:-}" | jq -R 'select(length > 0)' | jq -s '.')" \
    '{updated: $updated, conflicts: $conflicts, skipped: $skipped}'
fi
