#!/usr/bin/env bash
set -euo pipefail

# pr-status.sh — Show open agent PRs with test failures and review status
# Part of the pr-creation skill

show_help() {
  cat <<'USAGE'
Usage: pr-status.sh [options]

List open PRs with CI status, review decisions, and staleness info.

Options:
  --author <user>   Filter by author (default: @me)
  --label <label>   Filter by label
  --limit <n>       Max PRs to show (default: 20)
  --json            Output as JSON
  --help            Show this help

Examples:
  pr-status.sh
  pr-status.sh --author bot-agent --json
  pr-status.sh --label "agent-created"
USAGE
  exit 0
}

AUTHOR="@me"
LABEL=""
LIMIT=20
JSON_OUTPUT=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help) show_help ;;
    --author) AUTHOR="$2"; shift 2 ;;
    --label) LABEL="$2"; shift 2 ;;
    --limit) LIMIT="$2"; shift 2 ;;
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

# Build gh pr list command
GH_ARGS=(pr list --state open --author "$AUTHOR" --limit "$LIMIT")
GH_ARGS+=(--json "number,title,headRefName,updatedAt,reviewDecision,statusCheckRollup,isDraft,url")

if [[ -n "$LABEL" ]]; then
  GH_ARGS+=(--label "$LABEL")
fi

PR_DATA=$(gh "${GH_ARGS[@]}")

if [[ "$JSON_OUTPUT" == true ]]; then
  echo "$PR_DATA" | jq '.'
  exit 0
fi

# Human-readable output
PR_COUNT=$(echo "$PR_DATA" | jq 'length')

if [[ "$PR_COUNT" -eq 0 ]]; then
  echo "No open PRs found for author: $AUTHOR"
  exit 0
fi

echo "Open PRs ($PR_COUNT) — author: $AUTHOR"
echo "────────────────────────────────────────"

echo "$PR_DATA" | jq -r '.[] | [
  "#\(.number)",
  (if .isDraft then "[DRAFT]" else "" end),
  .title,
  "(\(.headRefName))",
  "review: \(.reviewDecision // "PENDING")",
  "checks: \(
    if (.statusCheckRollup | length) == 0 then "none"
    else
      ((.statusCheckRollup | map(select(.conclusion == "FAILURE")) | length) as $fail |
       (.statusCheckRollup | map(select(.conclusion == "SUCCESS")) | length) as $pass |
       (.statusCheckRollup | map(select(.conclusion == null or .conclusion == "PENDING")) | length) as $pending |
       if $fail > 0 then "\($fail) FAILED"
       elif $pending > 0 then "\($pending) pending"
       else "\($pass) passed" end)
    end
  )"
] | join("  ")' 2>/dev/null || echo "$PR_DATA" | jq -r '.[] | "#\(.number)  \(.title)  (\(.headRefName))"'

# Show rerun info for failed checks
FAILED_PRS=$(echo "$PR_DATA" | jq -r '.[] | select(.statusCheckRollup != null) | select([.statusCheckRollup[] | select(.conclusion == "FAILURE")] | length > 0) | "#\(.number) \(.headRefName)"')

if [[ -n "$FAILED_PRS" ]]; then
  echo ""
  echo "PRs with failed checks (rerun with: bash .ctx/skills/pr-creation/scripts/rerun-failed.sh --branch <name>):"
  echo "$FAILED_PRS"
fi
