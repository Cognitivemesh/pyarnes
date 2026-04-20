#!/usr/bin/env bash
set -euo pipefail

# pr-comments.sh — List PR review comments; interactive reply for Cursor/Claude
# Part of the pr-creation skill

show_help() {
  cat <<'USAGE'
Usage: pr-comments.sh <pr-number> [options]

List review comments on a PR. Optionally reply to a comment.

Arguments:
  pr-number              PR number (required)

Options:
  --reply <id> <body>    Reply to a specific comment
  --comment <body>       Add a general PR comment
  --json                 Output as JSON
  --help                 Show this help

Examples:
  pr-comments.sh 42
  pr-comments.sh 42 --json
  pr-comments.sh 42 --reply 123456 "Fixed in latest commit"
  pr-comments.sh 42 --comment "Ready for re-review"
USAGE
  exit 0
}

PR_NUMBER=""
REPLY_ID=""
REPLY_BODY=""
COMMENT_BODY=""
JSON_OUTPUT=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help) show_help ;;
    --reply) REPLY_ID="$2"; REPLY_BODY="$3"; shift 3 ;;
    --comment) COMMENT_BODY="$2"; shift 2 ;;
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

# Get repo info
REPO=$(gh repo view --json nameWithOwner -q '.nameWithOwner')

# Reply to a comment
if [[ -n "$REPLY_ID" ]]; then
  gh api "repos/${REPO}/pulls/comments/${REPLY_ID}/replies" \
    -f body="$REPLY_BODY" \
    --jq '.id' && echo " — reply posted" || { echo "Error: Failed to reply" >&2; exit 1; }
  exit 0
fi

# Add a general comment
if [[ -n "$COMMENT_BODY" ]]; then
  gh pr comment "$PR_NUMBER" --body "$COMMENT_BODY"
  echo "Comment posted on PR #${PR_NUMBER}"
  exit 0
fi

# List review comments
COMMENTS=$(gh api "repos/${REPO}/pulls/${PR_NUMBER}/comments" \
  --jq '.[] | {id, path, line: (.line // .original_line), body, user: .user.login, created_at, in_reply_to_id}')

if [[ "$JSON_OUTPUT" == true ]]; then
  gh api "repos/${REPO}/pulls/${PR_NUMBER}/comments"
  exit 0
fi

# Also get issue-level comments
ISSUE_COMMENTS=$(gh pr view "$PR_NUMBER" --json comments --jq '.comments[] | "[\(.author.login)] \(.body[0:200])"' 2>/dev/null || true)

echo "Review comments on PR #${PR_NUMBER}"
echo "────────────────────────────────────"

if [[ -z "$COMMENTS" ]]; then
  echo "(no inline review comments)"
else
  echo "$COMMENTS" | jq -r '"[\(.user)] \(.path):\(.line // "?") (id:\(.id))\n  \(.body[0:200])\n"' 2>/dev/null || echo "$COMMENTS"
fi

if [[ -n "$ISSUE_COMMENTS" ]]; then
  echo ""
  echo "General comments:"
  echo "$ISSUE_COMMENTS"
fi

echo ""
echo "Reply with: pr-comments.sh $PR_NUMBER --reply <comment-id> \"your reply\""
