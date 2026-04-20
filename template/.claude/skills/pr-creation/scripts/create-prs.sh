#!/usr/bin/env bash
set -euo pipefail

# create-prs.sh — Find recent agent branches and create PRs from them
# Part of the pr-creation skill

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

show_help() {
  cat <<'USAGE'
Usage: create-prs.sh [options]

Find remote branches matching agent naming patterns that don't have PRs,
and create PRs for them. Uses pr-submit.sh for spec-driven submission
when a matching spec file is found.

Options:
  --pattern <glob>     Branch pattern (default: feat/*,fix/*,chore/*)
  --spec-dir <path>    Spec directory to search (default: specs/)
  --draft              Create PRs as drafts
  --dry-run            List branches that would get PRs, without creating them
  --json               Output as JSON
  --help               Show this help

Examples:
  create-prs.sh
  create-prs.sh --pattern "agent/*"
  create-prs.sh --dry-run
  create-prs.sh --draft --spec-dir specs/
USAGE
  exit 0
}

PATTERNS="feat/*,fix/*,chore/*"
SPEC_DIR="specs/"
DRAFT=false
DRY_RUN=false
JSON_OUTPUT=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help) show_help ;;
    --pattern) PATTERNS="$2"; shift 2 ;;
    --spec-dir) SPEC_DIR="$2"; shift 2 ;;
    --draft) DRAFT=true; shift ;;
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

# Fetch latest remote refs
git fetch --prune origin 2>/dev/null

# Find remote branches matching patterns
BRANCHES=()
IFS=',' read -ra PATTERN_LIST <<< "$PATTERNS"
for pattern in "${PATTERN_LIST[@]}"; do
  while IFS= read -r branch; do
    [[ -n "$branch" ]] && BRANCHES+=("$branch")
  done < <(git branch -r --list "origin/${pattern}" 2>/dev/null | sed 's|^ *origin/||')
done

if [[ ${#BRANCHES[@]} -eq 0 ]]; then
  echo "No branches found matching patterns: $PATTERNS"
  exit 0
fi

# Filter out branches that already have PRs
NEW_BRANCHES=()
for branch in "${BRANCHES[@]}"; do
  EXISTING=$(gh pr list --head "$branch" --state open --json number --jq 'length' 2>/dev/null || echo "0")
  if [[ "$EXISTING" -eq 0 ]]; then
    NEW_BRANCHES+=("$branch")
  fi
done

if [[ ${#NEW_BRANCHES[@]} -eq 0 ]]; then
  echo "All matching branches already have open PRs."
  exit 0
fi

echo "Found ${#NEW_BRANCHES[@]} branch(es) without PRs:"
printf '  - %s\n' "${NEW_BRANCHES[@]}"

if [[ "$DRY_RUN" == true ]]; then
  if [[ "$JSON_OUTPUT" == true ]]; then
    printf '%s\n' "${NEW_BRANCHES[@]}" | jq -R . | jq -s '{branches: ., dry_run: true}'
  fi
  exit 0
fi

echo ""
CREATED=()
FAILED=()

for branch in "${NEW_BRANCHES[@]}"; do
  echo "Creating PR for: $branch"

  # Try to find a matching spec file
  SPEC_FILE=""
  if [[ -d "$SPEC_DIR" ]]; then
    # Match by branch name in spec metadata or filename
    SPEC_FILE=$(grep -rl "Branch.*${branch}" "$SPEC_DIR"/*.md 2>/dev/null | head -1 || true)
    if [[ -z "$SPEC_FILE" ]]; then
      # Try matching by branch name slug in filename
      BRANCH_SLUG=$(echo "$branch" | sed 's|/|-|g')
      SPEC_FILE=$(find "$SPEC_DIR" -name "*${BRANCH_SLUG}*" -type f 2>/dev/null | head -1 || true)
    fi
  fi

  if [[ -n "$SPEC_FILE" ]]; then
    # Use pr-submit.sh for spec-driven submission
    echo "  Found spec: $SPEC_FILE"
    SUBMIT_ARGS=(--spec "$SPEC_FILE" --branch "$branch")
    [[ "$DRAFT" == true ]] && SUBMIT_ARGS+=(--draft)

    if bash "${SCRIPT_DIR}/pr-submit.sh" "${SUBMIT_ARGS[@]}"; then
      CREATED+=("$branch")
    else
      FAILED+=("$branch")
    fi
  else
    # Create with auto-generated body
    echo "  No spec found, creating with auto-generated body"
    # Get recent commits on this branch
    COMMITS=$(git log "origin/main..origin/${branch}" --oneline 2>/dev/null | head -10 || echo "No commits found")

    BODY="## Summary

Auto-created PR for branch \`${branch}\`.

### Commits
\`\`\`
${COMMITS}
\`\`\`

---
*Created by create-prs.sh*"

    # Derive title from branch name
    TITLE=$(echo "$branch" | sed 's|^[^/]*/||; s|-| |g; s|_| |g')

    GH_ARGS=(pr create --title "$TITLE" --base main --head "$branch" --body "$BODY")
    [[ "$DRAFT" == true ]] && GH_ARGS+=(--draft)

    if gh "${GH_ARGS[@]}"; then
      CREATED+=("$branch")
    else
      FAILED+=("$branch")
    fi
  fi
  echo ""
done

echo "────────────────────────────────────"
echo "Created: ${#CREATED[@]}  Failed: ${#FAILED[@]}"

if [[ ${#FAILED[@]} -gt 0 ]]; then
  echo "Failed branches:"
  printf '  - %s\n' "${FAILED[@]}"
fi

if [[ "$JSON_OUTPUT" == true ]]; then
  jq -n \
    --argjson created "$(printf '%s\n' "${CREATED[@]}" | jq -R . | jq -s .)" \
    --argjson failed "$(printf '%s\n' "${FAILED[@]}" | jq -R . | jq -s .)" \
    '{created: $created, failed: $failed}'
fi
