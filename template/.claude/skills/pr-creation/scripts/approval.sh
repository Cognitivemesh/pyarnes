#!/usr/bin/env bash
set -euo pipefail

# approval.sh — Trigger merge when PR is ready (auto-merge / merge queue)
# Part of the pr-creation skill

show_help() {
  cat <<'USAGE'
Usage: approval.sh <pr-number> [options]

Check if a PR is approved with passing checks, then enable auto-merge
or add to merge queue.

Arguments:
  pr-number              PR number (required)

Options:
  --strategy <type>      Merge strategy: squash (default), merge, rebase
  --queue                Use merge queue instead of auto-merge
  --dry-run              Check readiness without triggering merge
  --json                 Output as JSON
  --help                 Show this help

Examples:
  approval.sh 42                          # Auto-merge with squash
  approval.sh 42 --strategy rebase
  approval.sh 42 --queue
  approval.sh 42 --dry-run                # Just check readiness
USAGE
  exit 0
}

PR_NUMBER=""
STRATEGY="squash"
USE_QUEUE=false
DRY_RUN=false
JSON_OUTPUT=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help) show_help ;;
    --strategy) STRATEGY="$2"; shift 2 ;;
    --queue) USE_QUEUE=true; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    --json) JSON_OUTPUT=true; shift ;;
    -*) echo "Unknown option: $1" >&2; exit 1 ;;
    *)
      if [[ -z "$PR_NUMBER" ]]; then
        PR_NUMBER="$1"
      else
        echo "Unexpected argument: $1" >&2; exit 1
      fi
      shift ;;
  esac
done

if [[ -z "$PR_NUMBER" ]]; then
  echo "Error: PR number is required. Use --help for usage." >&2
  exit 1
fi

# Check gh auth
if ! gh auth status &>/dev/null; then
  echo "Error: Not authenticated with GitHub CLI. Run 'gh auth login'." >&2
  exit 1
fi

# Get PR status
PR_INFO=$(gh pr view "$PR_NUMBER" --json "state,reviewDecision,statusCheckRollup,mergeable,title,headRefName,isDraft")

STATE=$(echo "$PR_INFO" | jq -r '.state')
REVIEW=$(echo "$PR_INFO" | jq -r '.reviewDecision // "PENDING"')
MERGEABLE=$(echo "$PR_INFO" | jq -r '.mergeable')
IS_DRAFT=$(echo "$PR_INFO" | jq -r '.isDraft')
TITLE=$(echo "$PR_INFO" | jq -r '.title')
BRANCH=$(echo "$PR_INFO" | jq -r '.headRefName')

# Count check statuses
CHECKS_TOTAL=$(echo "$PR_INFO" | jq '[.statusCheckRollup // [] | .[] ] | length')
CHECKS_PASS=$(echo "$PR_INFO" | jq '[.statusCheckRollup // [] | .[] | select(.conclusion == "SUCCESS")] | length')
CHECKS_FAIL=$(echo "$PR_INFO" | jq '[.statusCheckRollup // [] | .[] | select(.conclusion == "FAILURE")] | length')
CHECKS_PENDING=$(echo "$PR_INFO" | jq '[.statusCheckRollup // [] | .[] | select(.conclusion == null or .conclusion == "PENDING")] | length')

# Determine readiness
READY=true
BLOCKERS=()

if [[ "$STATE" != "OPEN" ]]; then
  READY=false
  BLOCKERS+=("PR is $STATE (not open)")
fi

if [[ "$IS_DRAFT" == "true" ]]; then
  READY=false
  BLOCKERS+=("PR is a draft")
fi

if [[ "$REVIEW" != "APPROVED" ]]; then
  READY=false
  BLOCKERS+=("Review: $REVIEW (needs APPROVED)")
fi

if [[ "$CHECKS_FAIL" -gt 0 ]]; then
  READY=false
  BLOCKERS+=("$CHECKS_FAIL check(s) failed")
fi

if [[ "$CHECKS_PENDING" -gt 0 ]]; then
  READY=false
  BLOCKERS+=("$CHECKS_PENDING check(s) still pending")
fi

if [[ "$MERGEABLE" != "MERGEABLE" ]]; then
  READY=false
  BLOCKERS+=("Mergeable state: $MERGEABLE")
fi

# Output
if [[ "$JSON_OUTPUT" == true ]]; then
  jq -n \
    --arg pr "$PR_NUMBER" \
    --arg title "$TITLE" \
    --arg branch "$BRANCH" \
    --argjson ready "$READY" \
    --arg review "$REVIEW" \
    --arg mergeable "$MERGEABLE" \
    --argjson checks_pass "$CHECKS_PASS" \
    --argjson checks_fail "$CHECKS_FAIL" \
    --argjson checks_pending "$CHECKS_PENDING" \
    --argjson blockers "$(printf '%s\n' "${BLOCKERS[@]}" | jq -R . | jq -s .)" \
    '{pr: $pr, title: $title, branch: $branch, ready: $ready, review: $review, mergeable: $mergeable, checks: {pass: $checks_pass, fail: $checks_fail, pending: $checks_pending}, blockers: $blockers}'
  if [[ "$DRY_RUN" == true || "$READY" != true ]]; then
    exit 0
  fi
fi

if [[ "$DRY_RUN" == true ]]; then
  echo "PR #${PR_NUMBER}: ${TITLE} (${BRANCH})"
  echo "────────────────────────────────────"
  echo "Review:    $REVIEW"
  echo "Checks:    $CHECKS_PASS passed, $CHECKS_FAIL failed, $CHECKS_PENDING pending"
  echo "Mergeable: $MERGEABLE"
  echo ""
  if [[ "$READY" == true ]]; then
    echo "READY to merge"
  else
    echo "NOT READY — blockers:"
    printf '  - %s\n' "${BLOCKERS[@]}"
  fi
  exit 0
fi

# Block if not ready
if [[ "$READY" != true ]]; then
  echo "PR #${PR_NUMBER} is NOT ready to merge:" >&2
  printf '  - %s\n' "${BLOCKERS[@]}" >&2
  exit 1
fi

# Trigger merge
echo "PR #${PR_NUMBER} is ready. Enabling auto-merge..."

if [[ "$USE_QUEUE" == true ]]; then
  gh pr merge "$PR_NUMBER" --auto --"$STRATEGY"
  echo "Added to merge queue with strategy: $STRATEGY"
else
  gh pr merge "$PR_NUMBER" --auto --"$STRATEGY"
  echo "Auto-merge enabled with strategy: $STRATEGY"
fi
