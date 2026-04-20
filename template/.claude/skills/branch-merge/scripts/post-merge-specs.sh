#!/usr/bin/env bash
set -euo pipefail

# post-merge-specs.sh — Automate Step 6 of branch-merge: post-merge spec updates
# Usage: post-merge-specs.sh <branch-name> [--dry-run] [--date YYYY-MM-DD]
#
# After a branch is merged to main, this script:
#   1. Resolves the branch name to a spec file (via INDEX.md Branch column)
#   2. Verifies the branch is actually merged
#   3. Updates the spec's Status metadata to MERGED
#   4. Updates the Implementation Checkpoint workstreams to CLOSED
#   5. Moves the spec to archive/
#   6. Updates INDEX.md links and status
#   7. Updates Tier Overview summaries

REPO_ROOT="$(git rev-parse --show-toplevel)"
SPECS_DIR="$REPO_ROOT/specs"
INDEX_FILE="$SPECS_DIR/INDEX.md"
ARCHIVE_DIR="$SPECS_DIR/archive"
TODAY="$(date +%Y-%m-%d)"

BRANCH_NAME=""
DRY_RUN=false
MERGE_DATE="$TODAY"

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --date)
      # Next arg will be the date; handled below
      ;;
    --help|-h)
      echo "Usage: post-merge-specs.sh <branch-name> [--dry-run] [--date YYYY-MM-DD]"
      echo ""
      echo "  branch-name    The merged branch name"
      echo "  --dry-run      Show what would change without modifying files"
      echo "  --date         Override merge date (default: today)"
      exit 0
      ;;
    -*) ;;
    *)
      if [ -z "$BRANCH_NAME" ]; then
        BRANCH_NAME="$arg"
      else
        # Could be the date value after --date
        MERGE_DATE="$arg"
      fi
      ;;
  esac
done

# Handle --date with value
ARGS=("$@")
for i in "${!ARGS[@]}"; do
  if [ "${ARGS[$i]}" = "--date" ] && [ -n "${ARGS[$((i+1))]:-}" ]; then
    MERGE_DATE="${ARGS[$((i+1))]}"
  fi
done

if [ -z "$BRANCH_NAME" ]; then
  echo "Usage: post-merge-specs.sh <branch-name> [--dry-run] [--date YYYY-MM-DD]"
  exit 1
fi

echo "Post-merge spec update for: $BRANCH_NAME"
echo "Merge date: $MERGE_DATE"
if [ "$DRY_RUN" = true ]; then
  echo "(DRY RUN — no files will be modified)"
fi
echo ""

# ═══════════════════════════════════════════════════════════
# Step 1: Resolve branch to spec file
# ═══════════════════════════════════════════════════════════

SPEC_FILE=""
PR_NUMBER=""

# Strategy 1: Search INDEX.md for the branch name in the Branch column
INDEX_LINE="$(grep -E "\`$BRANCH_NAME\`" "$INDEX_FILE" 2>/dev/null | head -1 || true)"
if [ -n "$INDEX_LINE" ]; then
  # Extract the spec link from this line
  SPEC_LINK="$(echo "$INDEX_LINE" | grep -oE '\[PR-[^]]+\]\([^)]+\.md\)' | head -1 || true)"
  if [ -n "$SPEC_LINK" ]; then
    SPEC_PATH="$(echo "$SPEC_LINK" | grep -oE '\([^)]+\.md\)' | tr -d '()')"
    PR_NUMBER="$(echo "$SPEC_LINK" | grep -oE 'PR-[0-9A-Z-]+' | head -1)"
    SPEC_FILE="$SPECS_DIR/$SPEC_PATH"
  fi
fi

# Strategy 2: Search spec files directly for the branch name in metadata
if [ -z "$SPEC_FILE" ] || [ ! -f "$SPEC_FILE" ]; then
  SPEC_FILE="$(grep -rlE "\`$BRANCH_NAME\`" "$SPECS_DIR"/PR-*.md 2>/dev/null | head -1 || true)"
  if [ -n "$SPEC_FILE" ]; then
    PR_NUMBER="$(basename "$SPEC_FILE" | grep -oE 'PR-[0-9A-Z-]+' | head -1)"
  fi
fi

# Strategy 3: Try to extract PR number from branch convention
if [ -z "$SPEC_FILE" ]; then
  # Pattern: feat/0.2.XX-name -> find PR matching that version
  echo "WARNING: Could not find spec matching branch '$BRANCH_NAME'"
  echo "Searched INDEX.md Branch column and spec metadata tables."
  echo ""
  echo "Try running manually with the spec file path:"
  echo "  bash .ctx/skills/update-specs/scripts/spec-sync.sh pr-status <PR-number> '**Merged** ($MERGE_DATE)'"
  exit 0
fi

if [ ! -f "$SPEC_FILE" ]; then
  echo "WARNING: Spec file not found at: $SPEC_FILE"
  echo "It may have already been archived."
  exit 0
fi

echo "Found spec: $(basename "$SPEC_FILE") ($PR_NUMBER)"

# ═══════════════════════════════════════════════════════════
# Step 2: Verify merge status
# ═══════════════════════════════════════════════════════════

# Check if the branch still has unmerged commits
UNMERGED="$(git log --oneline "main..$BRANCH_NAME" 2>/dev/null || true)"
if [ -n "$UNMERGED" ]; then
  echo ""
  echo "WARNING: Branch '$BRANCH_NAME' has unmerged commits:"
  echo "$UNMERGED" | head -5
  echo ""
  echo "This branch may not be fully merged. Proceeding anyway..."
  echo "(If this is a squash-merge, unmerged commits are expected)"
fi

# ═══════════════════════════════════════════════════════════
# Step 3: Update spec Status metadata
# ═══════════════════════════════════════════════════════════

MERGED_STATUS="**MERGED** ($MERGE_DATE)"

if [ "$DRY_RUN" = false ]; then
  if grep -qE '^\| \*\*Status\*\*' "$SPEC_FILE"; then
    sed -i '' "s/^| \*\*Status\*\* |.*/| **Status** | $MERGED_STATUS |/" "$SPEC_FILE"
    echo "Updated spec Status -> $MERGED_STATUS"
  else
    # Add Status row after the last metadata row
    LAST_META="$(grep -n '^|' "$SPEC_FILE" | head -20 | tail -1 | cut -d: -f1)"
    if [ -n "$LAST_META" ]; then
      sed -i '' "${LAST_META}a\\| **Status** | $MERGED_STATUS |" "$SPEC_FILE"
      echo "Added Status row -> $MERGED_STATUS"
    fi
  fi
else
  echo "[DRY RUN] Would update spec Status -> $MERGED_STATUS"
fi

# ═══════════════════════════════════════════════════════════
# Step 4: Update Implementation Checkpoint
# ═══════════════════════════════════════════════════════════

if [ "$DRY_RUN" = false ]; then
  # Replace remaining ⬜ with CLOSED in workstream tables
  if grep -q '⬜' "$SPEC_FILE" 2>/dev/null; then
    sed -i '' "s/| ⬜ |/| CLOSED | Merged to main $MERGE_DATE |/g" "$SPEC_FILE"
    echo "Closed remaining workstreams"
  fi

  # Update Progress header
  if grep -q '^### Progress$' "$SPEC_FILE" 2>/dev/null; then
    sed -i '' 's/^### Progress$/### Progress (Completed)/' "$SPEC_FILE"
    echo "Updated Progress -> Progress (Completed)"
  fi
else
  echo "[DRY RUN] Would close remaining workstreams and update Progress header"
fi

# ═══════════════════════════════════════════════════════════
# Step 5: Move spec to archive/
# ═══════════════════════════════════════════════════════════

SPEC_BASENAME="$(basename "$SPEC_FILE")"
ARCHIVE_PATH="$ARCHIVE_DIR/$SPEC_BASENAME"

if [ "$DRY_RUN" = false ]; then
  mkdir -p "$ARCHIVE_DIR"
  if [ -f "$SPEC_FILE" ] && ! echo "$SPEC_FILE" | grep -q "/archive/"; then
    mv "$SPEC_FILE" "$ARCHIVE_PATH"
    echo "Moved to archive: $SPEC_BASENAME -> archive/$SPEC_BASENAME"
  elif echo "$SPEC_FILE" | grep -q "/archive/"; then
    echo "Already in archive: $SPEC_BASENAME"
  fi
else
  echo "[DRY RUN] Would move $SPEC_BASENAME -> archive/$SPEC_BASENAME"
fi

# ═══════════════════════════════════════════════════════════
# Step 6: Update INDEX.md links and status
# ═══════════════════════════════════════════════════════════

INDEX_STATUS="**Merged** ($MERGE_DATE)"

if [ "$DRY_RUN" = false ]; then
  # Update link path: (PR-NN-name.md) -> (archive/PR-NN-name.md)
  # Only if not already pointing to archive/
  if grep -qE "\($SPEC_BASENAME\)" "$INDEX_FILE" 2>/dev/null; then
    sed -i '' "s|($SPEC_BASENAME)|(archive/$SPEC_BASENAME)|g" "$INDEX_FILE"
    echo "Updated INDEX.md link -> archive/$SPEC_BASENAME"
  fi

  # Update status column in the PR's INDEX row
  LINE_NUM="$(grep -nE "^\| \[$PR_NUMBER\]" "$INDEX_FILE" | head -1 | cut -d: -f1 || true)"
  if [ -n "$LINE_NUM" ]; then
    sed -i '' "${LINE_NUM}s/| [^|]* |$/| $INDEX_STATUS |/" "$INDEX_FILE"
    echo "Updated INDEX.md status -> $INDEX_STATUS"
  fi
else
  echo "[DRY RUN] Would update INDEX.md link and status for $PR_NUMBER"
fi

# ═══════════════════════════════════════════════════════════
# Step 7: Update Tier Overview summaries
# ═══════════════════════════════════════════════════════════

if [ "$DRY_RUN" = false ]; then
  # Use spec-sync's tier summary logic if available
  SYNC_SCRIPT="$(dirname "$0")/../../update-specs/scripts/spec-sync.sh"
  if [ -x "$SYNC_SCRIPT" ]; then
    # spec-sync pr-status updates tier summaries as a side effect,
    # but we've already done the status update manually above.
    # Just recount tiers directly.
    :
  fi

  # Inline tier summary update
  for tier_num in 1 2 3 4 5 6 7; do
    tier_total=0
    tier_merged=0

    in_tier=false
    while IFS= read -r line; do
      if echo "$line" | grep -qE "^### Tier $tier_num "; then
        in_tier=true
        continue
      fi
      if [ "$in_tier" = true ] && echo "$line" | grep -qE '^### '; then
        break
      fi
      if [ "$in_tier" = true ] && echo "$line" | grep -qE '^\| \[PR-'; then
        ((tier_total++)) || true
        if echo "$line" | grep -qi "merged"; then
          ((tier_merged++)) || true
        fi
      fi
    done < "$INDEX_FILE"

    if [ "$tier_total" -eq 0 ]; then continue; fi

    if [ "$tier_merged" -eq "$tier_total" ]; then
      new_overview="**Complete** — all $tier_total PRs merged"
    elif [ "$tier_merged" -gt 0 ]; then
      new_overview="Partial — $tier_merged/$tier_total merged"
    else
      continue  # Don't update if nothing merged
    fi

    # Update Tier Overview table
    if grep -qE "^\| \*\*$tier_num\*\* \|" "$INDEX_FILE"; then
      sed -i '' -E "/^\| \*\*$tier_num\*\* \|/s/\| [^|]+ \|$/| $new_overview |/" "$INDEX_FILE"
    fi
  done
  echo "Updated Tier Overview summaries"
else
  echo "[DRY RUN] Would update Tier Overview summaries"
fi

# ═══════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  Post-Merge Spec Update Summary"
echo "═══════════════════════════════════════════════════════════"
echo "  Branch:  $BRANCH_NAME"
echo "  Spec:    $PR_NUMBER ($SPEC_BASENAME)"
echo "  Date:    $MERGE_DATE"
if [ "$DRY_RUN" = true ]; then
  echo "  Mode:    DRY RUN (no changes made)"
else
  echo "  Actions: Status updated, archived, INDEX.md synced"
fi
echo "═══════════════════════════════════════════════════════════"

if [ "$DRY_RUN" = false ]; then
  echo ""
  echo "Verify changes:"
  echo "  git diff specs/"
  echo "  bash .ctx/skills/update-specs/scripts/spec-lint.sh --verbose"
fi
