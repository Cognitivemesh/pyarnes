#!/usr/bin/env bash
set -euo pipefail

# pr-submit.sh — Submit a PR with spec-driven body
#
# Reads the spec file to extract title and summary, pushes the branch,
# and creates the PR via gh CLI with a conventional format.
#
# Usage: pr-submit.sh --spec <path> --branch <name> [--draft] [--json]
#
# Exit codes:
#   0  PR created successfully
#   1  Error (details printed)

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

SPEC_PATH=""
BRANCH_NAME=""
DRAFT=false
JSON_OUTPUT=false

show_help() {
  cat <<'USAGE'
Usage: pr-submit.sh --spec <path> --branch <name> [--draft] [--json]

Options:
  --spec <path>     Path to the PR spec file (e.g. specs/PR-15-todo-cleanup-a.md)
  --branch <name>   Branch name to push and create PR from
  --draft           Create as draft PR
  --json            Output result as JSON
  --help            Show this help

Examples:
  pr-submit.sh --spec specs/PR-15-todo-cleanup-a.md --branch feat/0.2.25-todo-cleanup
  pr-submit.sh --spec specs/PR-16-svg-export.md --branch feat/0.2.26-svg-export --draft
USAGE
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h) show_help ;;
    --spec) SPEC_PATH="$2"; shift 2 ;;
    --branch) BRANCH_NAME="$2"; shift 2 ;;
    --draft) DRAFT=true; shift ;;
    --json) JSON_OUTPUT=true; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

if [ -z "$SPEC_PATH" ] || [ -z "$BRANCH_NAME" ]; then
  echo "Error: --spec and --branch are required"
  echo "Run with --help for usage"
  exit 1
fi

if [ ! -f "$SPEC_PATH" ]; then
  echo "Error: Spec file not found: $SPEC_PATH"
  exit 1
fi

# ── Check gh CLI auth ─────────────────────────────────────
if ! gh auth status &>/dev/null; then
  echo "Error: gh CLI not authenticated. Run: gh auth login"
  exit 1
fi

# ── Extract spec metadata ─────────────────────────────────
SPEC_FILENAME="$(basename "$SPEC_PATH" .md)"

# Extract the PR title from the first H1 heading
PR_TITLE=$(head -5 "$SPEC_PATH" | grep '^# ' | head -1 | sed 's/^# //')
if [ -z "$PR_TITLE" ]; then
  PR_TITLE="$SPEC_FILENAME"
fi

# Extract summary section (first paragraph after ## Summary)
SUMMARY=$(awk '/^## Summary/{found=1; next} found && /^---/{exit} found && /^## /{exit} found{print}' "$SPEC_PATH" | head -10 | sed '/^$/d')
if [ -z "$SUMMARY" ]; then
  SUMMARY="Implements $SPEC_FILENAME"
fi

# Extract estimated size
EST_SIZE=$(grep -i 'Estimated Size' "$SPEC_PATH" | head -1 | sed 's/.*|[^|]*|[[:space:]]*//' | sed 's/[[:space:]]*|$//' || echo "unknown")

# ── Push branch ───────────────────────────────────────────
echo "Pushing branch $BRANCH_NAME..."
git push -u origin "$BRANCH_NAME"

# ── Create PR ─────────────────────────────────────────────
DRAFT_FLAG=""
if [ "$DRAFT" = true ]; then
  DRAFT_FLAG="--draft"
fi

echo "Creating PR..."
PR_URL=$(gh pr create \
  --title "$PR_TITLE" \
  --base main \
  --head "$BRANCH_NAME" \
  $DRAFT_FLAG \
  --body "$(cat <<EOF
## Summary

$SUMMARY

**Spec**: [$SPEC_FILENAME]($SPEC_PATH)
**Estimated size**: $EST_SIZE

## Verification

- [ ] \`make toolbox-typecheck\` — 22/22 pass
- [ ] \`make toolbox-check\` — 0 errors
- [ ] \`make toolbox-ci-all\` — green
- [ ] No new TODO markers introduced

## Test plan

- [ ] Existing tests pass (test freeze policy)
- [ ] Pre-flight quality gate passed (\`pr-preflight.sh\`)

Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)")

echo ""
echo "PR created: $PR_URL"

# ── JSON output ───────────────────────────────────────────
if [ "$JSON_OUTPUT" = true ]; then
  PR_NUMBER=$(echo "$PR_URL" | grep -oE '[0-9]+$')
  PR_STATE="OPEN"
  if [ "$DRAFT" = true ]; then
    PR_STATE="DRAFT"
  fi
  cat <<JSON
{"url":"$PR_URL","number":$PR_NUMBER,"state":"$PR_STATE","branch":"$BRANCH_NAME","spec":"$SPEC_PATH"}
JSON
fi
