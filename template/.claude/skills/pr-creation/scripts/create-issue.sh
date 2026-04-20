#!/usr/bin/env bash
set -euo pipefail

# create-issue.sh — Create an issue and instruct a specified agent to build it
# Part of the pr-creation skill

show_help() {
  cat <<'USAGE'
Usage: create-issue.sh --title <title> --agent <name> [options]

Create a GitHub issue with implementation instructions for a target agent.

Required:
  --title <title>      Issue title
  --agent <name>       Target agent (e.g., claude, cursor, copilot)

Options:
  --body <text>        Issue body / description
  --spec <path>        Include spec file content in the issue body
  --label <label>      Add label(s) — can be repeated
  --milestone <name>   Assign to milestone
  --branch <name>      Suggested branch name for the agent
  --priority <p>       Priority hint: high, medium, low (default: medium)
  --json               Output as JSON
  --help               Show this help

Examples:
  create-issue.sh --title "Add retry logic" --agent claude
  create-issue.sh --title "Fix auth flow" --agent cursor --spec specs/PR-50.md
  create-issue.sh --title "Update deps" --agent claude --label "agent-task" --label "chore"
USAGE
  exit 0
}

TITLE=""
AGENT=""
BODY=""
SPEC_PATH=""
LABELS=()
MILESTONE=""
BRANCH_HINT=""
PRIORITY="medium"
JSON_OUTPUT=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help) show_help ;;
    --title) TITLE="$2"; shift 2 ;;
    --agent) AGENT="$2"; shift 2 ;;
    --body) BODY="$2"; shift 2 ;;
    --spec) SPEC_PATH="$2"; shift 2 ;;
    --label) LABELS+=("$2"); shift 2 ;;
    --milestone) MILESTONE="$2"; shift 2 ;;
    --branch) BRANCH_HINT="$2"; shift 2 ;;
    --priority) PRIORITY="$2"; shift 2 ;;
    --json) JSON_OUTPUT=true; shift ;;
    -*) echo "Unknown option: $1" >&2; exit 1 ;;
    *) echo "Unexpected argument: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$TITLE" ]]; then
  echo "Error: --title is required. Use --help for usage." >&2
  exit 1
fi

if [[ -z "$AGENT" ]]; then
  echo "Error: --agent is required. Use --help for usage." >&2
  exit 1
fi

# Check gh auth
if ! gh auth status &>/dev/null; then
  echo "Error: Not authenticated with GitHub CLI. Run 'gh auth login'." >&2
  exit 1
fi

# Build issue body
ISSUE_BODY="## Agent Instructions

**Target agent**: \`${AGENT}\`
**Priority**: ${PRIORITY}
"

if [[ -n "$BRANCH_HINT" ]]; then
  ISSUE_BODY+="**Suggested branch**: \`${BRANCH_HINT}\`
"
fi

ISSUE_BODY+="
### Task
${BODY:-Implement the changes described in this issue.}
"

# Include spec content if provided
if [[ -n "$SPEC_PATH" && -f "$SPEC_PATH" ]]; then
  SPEC_CONTENT=$(cat "$SPEC_PATH")
  ISSUE_BODY+="
### Spec Reference

<details>
<summary>Spec: $(basename "$SPEC_PATH")</summary>

${SPEC_CONTENT}

</details>
"
fi

ISSUE_BODY+="
### Acceptance Criteria
- [ ] Implementation matches the task description
- [ ] All CI checks pass (\`make toolbox-ci-all\`)
- [ ] Changes are on a feature branch (not main)
- [ ] PR is created with a clear summary

---
*Created by create-issue.sh for agent: ${AGENT}*"

# Build gh issue create command
GH_ARGS=(issue create --title "$TITLE" --body "$ISSUE_BODY")

for label in "${LABELS[@]}"; do
  GH_ARGS+=(--label "$label")
done

if [[ -n "$MILESTONE" ]]; then
  GH_ARGS+=(--milestone "$MILESTONE")
fi

# Create the issue
RESULT=$(gh "${GH_ARGS[@]}" 2>&1)
echo "$RESULT"

if [[ "$JSON_OUTPUT" == true ]]; then
  # Extract issue number from URL
  ISSUE_URL=$(echo "$RESULT" | grep -o 'https://[^ ]*' | head -1 || echo "")
  ISSUE_NUM=$(echo "$ISSUE_URL" | grep -o '[0-9]*$' || echo "")
  jq -n \
    --arg url "$ISSUE_URL" \
    --arg number "$ISSUE_NUM" \
    --arg agent "$AGENT" \
    --arg title "$TITLE" \
    --arg priority "$PRIORITY" \
    '{url: $url, number: $number, agent: $agent, title: $title, priority: $priority}'
fi
