#!/usr/bin/env bash
set -euo pipefail

# guard-pr-create.sh — Claude PreToolUse hook to enforce pr-preflight before gh pr create
#
# Reads tool input from stdin (Claude Code passes JSON with tool_input.command).
# Checks for a .pr-preflight-passed marker file (must exist and be < 1 hour old).
# Blocks gh pr create if preflight has not been run.
#
# Exit codes:
#   0 — Allow the command
#   2 — Block the command (denied)

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
MARKER_FILE="$REPO_ROOT/.pr-preflight-passed"
MAX_AGE_SECONDS=3600  # 1 hour

# Read tool input from stdin — pipe directly to jq (no intermediate variable)
COMMAND=$(jq -r '.tool_input.command // empty')

# Allow if no command or not a gh pr create command
if [ -z "$COMMAND" ] || ! echo "$COMMAND" | grep -qE '(^|\s|&&|\|)gh pr create'; then
  exit 0
fi

# Allow the pr-submit.sh script (it manages preflight internally)
if echo "$COMMAND" | grep -q '.ctx/skills/pr-creation/scripts/pr-submit.sh'; then
  exit 0
fi

# Check marker file exists
if [ ! -f "$MARKER_FILE" ]; then
  cat <<'DENY'
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"BLOCKED: Run pr-preflight.sh before submitting a PR. Execute: bash .ctx/skills/pr-creation/scripts/pr-preflight.sh"}}
DENY
  exit 2
fi

# Check marker is not stale (< 1 hour old)
# Cross-platform: try GNU date, then macOS stat, then Linux stat
MARKER_TIME=$(date -d "$(cat "$MARKER_FILE")" +%s 2>/dev/null \
  || stat -f %m "$MARKER_FILE" 2>/dev/null \
  || stat -c %Y "$MARKER_FILE" 2>/dev/null \
  || echo 0)
NOW=$(date +%s)
AGE=$((NOW - MARKER_TIME))

if [ "$AGE" -gt "$MAX_AGE_SECONDS" ]; then
  cat <<'DENY'
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"BLOCKED: pr-preflight marker is stale (> 1 hour). Re-run: bash .ctx/skills/pr-creation/scripts/pr-preflight.sh"}}
DENY
  exit 2
fi

# Marker is valid — allow
exit 0
