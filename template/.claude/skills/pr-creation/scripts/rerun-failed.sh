#!/usr/bin/env bash
set -euo pipefail

# rerun-failed.sh — Rerun failed workflow runs on recent agent branches
# Part of the pr-creation skill

show_help() {
  cat <<'USAGE'
Usage: rerun-failed.sh [options]

Rerun failed GitHub Actions workflow runs on agent branches.

Options:
  --branch <name>    Target a specific branch
  --all              Rerun across all open PR branches
  --failed-only      Only rerun failed jobs, not entire workflow (default: full rerun)
  --dry-run          List failed runs without rerunning
  --limit <n>        Max runs to process (default: 10)
  --json             Output as JSON
  --force-stale      Rerun even if run SHA does not match current HEAD (use with caution)
  --help             Show this help

Examples:
  rerun-failed.sh --branch feat/my-feature
  rerun-failed.sh --all
  rerun-failed.sh --all --dry-run
  rerun-failed.sh --branch feat/my-feature --failed-only
  rerun-failed.sh --branch feat/my-feature --force-stale
USAGE
  exit 0
}

BRANCH=""
ALL=false
FAILED_ONLY=false
DRY_RUN=false
LIMIT=10
JSON_OUTPUT=false
FORCE_STALE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help) show_help ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --all) ALL=true; shift ;;
    --failed-only) FAILED_ONLY=true; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    --limit) LIMIT="$2"; shift 2 ;;
    --json) JSON_OUTPUT=true; shift ;;
    --force-stale) FORCE_STALE=true; shift ;;
    -*) echo "Unknown option: $1" >&2; exit 1 ;;
    *) echo "Unexpected argument: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$BRANCH" && "$ALL" != true ]]; then
  echo "Error: Specify --branch <name> or --all. Use --help for usage." >&2
  exit 1
fi

# Check gh auth
if ! gh auth status &>/dev/null; then
  echo "Error: Not authenticated with GitHub CLI. Run 'gh auth login'." >&2
  exit 1
fi

# Collect target branches
BRANCHES=()
if [[ "$ALL" == true ]]; then
  while IFS= read -r b; do
    [[ -n "$b" ]] && BRANCHES+=("$b")
  done < <(gh pr list --state open --json headRefName --jq '.[].headRefName')
else
  BRANCHES=("$BRANCH")
fi

if [[ ${#BRANCHES[@]} -eq 0 ]]; then
  echo "No branches to process."
  exit 0
fi

RERUN_COUNT=0
TOTAL_FAILED=0
RESULTS=()

for branch in "${BRANCHES[@]}"; do
  # Get failed runs for this branch
  FAILED_RUNS=$(gh run list --branch "$branch" --status failure --limit "$LIMIT" \
    --json databaseId,name,conclusion,headBranch,createdAt,headSha 2>/dev/null || echo "[]")

  RUN_COUNT=$(echo "$FAILED_RUNS" | jq 'length')

  if [[ "$RUN_COUNT" -eq 0 ]]; then
    continue
  fi

  TOTAL_FAILED=$((TOTAL_FAILED + RUN_COUNT))

  echo "Branch: $branch — $RUN_COUNT failed run(s)"

  echo "$FAILED_RUNS" | jq -r '.[] | "  [\(.databaseId)] \(.name) — \(.conclusion) (\(.createdAt))"'

  if [[ "$DRY_RUN" != true ]]; then
    CURRENT_SHA="$(git rev-parse "origin/$branch" 2>/dev/null || echo "")"
    while IFS= read -r run_id run_head_sha; do
      [[ -z "$run_id" ]] && continue
      # Stale SHA detection
      if [ -n "$CURRENT_SHA" ] && [ -n "$run_head_sha" ] && [ "$run_head_sha" != "$CURRENT_SHA" ]; then
        if [[ "$FORCE_STALE" == true ]]; then
          echo "  WARN: run $run_id is on stale SHA ${run_head_sha:0:8} (HEAD: ${CURRENT_SHA:0:8}) — proceeding due to --force-stale"
        else
          echo "  SKIP: run $run_id is on stale SHA ${run_head_sha:0:8} (current HEAD: ${CURRENT_SHA:0:8})"
          echo "        Push your fix and wait ~60s for a new run, or pass --force-stale to override."
          continue
        fi
      fi
      echo "  Rerunning: $run_id"
      if [[ "$FAILED_ONLY" == true ]]; then
        gh run rerun "$run_id" --failed 2>/dev/null && RERUN_COUNT=$((RERUN_COUNT + 1)) || echo "    Failed to rerun $run_id" >&2
      else
        gh run rerun "$run_id" 2>/dev/null && RERUN_COUNT=$((RERUN_COUNT + 1)) || echo "    Failed to rerun $run_id" >&2
      fi
    done < <(echo "$FAILED_RUNS" | jq -r '.[] | "\(.databaseId) \(.headSha)"')
  fi

  RESULTS+=("{\"branch\":\"$branch\",\"failed_runs\":$RUN_COUNT}")
  echo ""
done

echo "────────────────────────────────────"
if [[ "$DRY_RUN" == true ]]; then
  echo "Dry run: $TOTAL_FAILED failed run(s) across ${#BRANCHES[@]} branch(es)"
else
  echo "Rerun: $RERUN_COUNT of $TOTAL_FAILED failed run(s)"
fi

if [[ "$JSON_OUTPUT" == true ]]; then
  RESULTS_JSON=$(printf '%s\n' "${RESULTS[@]}" | jq -s '.')
  jq -n \
    --argjson results "$RESULTS_JSON" \
    --argjson rerun_count "$RERUN_COUNT" \
    --argjson total_failed "$TOTAL_FAILED" \
    --argjson dry_run "$DRY_RUN" \
    '{results: $results, rerun_count: $rerun_count, total_failed: $total_failed, dry_run: $dry_run}'
fi
