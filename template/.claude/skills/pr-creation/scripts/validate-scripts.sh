#!/usr/bin/env bash
set -euo pipefail

# validate-scripts.sh — Quantitative validation gate for skill scripts
# Runs 39 checks across 6 layers; prints scorecard. Exit 0 if all pass.

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

# ── Script inventory ─────────────────────────────────────────────────
AGENT_BROWSER_SCRIPTS=(
  .ctx/skills/agent-browser/scripts/browse.sh
  .ctx/skills/agent-browser/scripts/scrape.sh
  .ctx/skills/agent-browser/scripts/interact.sh
)

PR_LIFECYCLE_SCRIPTS=(
  .ctx/skills/pr-creation/scripts/pr-status.sh
  .ctx/skills/pr-creation/scripts/pr-comments.sh
  .ctx/skills/pr-creation/scripts/approval.sh
  .ctx/skills/pr-creation/scripts/create-prs.sh
  .ctx/skills/pr-creation/scripts/rerun-failed.sh
  .ctx/skills/pr-creation/scripts/create-issue.sh
  .ctx/skills/pr-creation/scripts/update-main.sh
)

ALL_SCRIPTS=("${AGENT_BROWSER_SCRIPTS[@]}" "${PR_LIFECYCLE_SCRIPTS[@]}")

# Scripts that MUST fail when invoked without arguments
REQUIRED_ARG_SCRIPTS=(
  .ctx/skills/agent-browser/scripts/scrape.sh
  .ctx/skills/agent-browser/scripts/interact.sh
  .ctx/skills/pr-creation/scripts/pr-comments.sh
  .ctx/skills/pr-creation/scripts/approval.sh
  .ctx/skills/pr-creation/scripts/rerun-failed.sh
  .ctx/skills/pr-creation/scripts/create-issue.sh
)

# ── Counters ──────────────────────────────────────────────────────────
TOTAL=0
PASSED=0
FAILED_DETAILS=()

pass() { TOTAL=$((TOTAL + 1)); PASSED=$((PASSED + 1)); echo "  PASS: $1"; }
fail() { TOTAL=$((TOTAL + 1)); FAILED_DETAILS+=("$1"); echo "  FAIL: $1"; }

# ── Layer 1: Shell Syntax (bash -n) ──────────────────────────────────
echo ""
echo "═══ Layer 1: Shell Syntax (bash -n) ═══"
L1_PASS=0; L1_TOTAL=0
for f in "${ALL_SCRIPTS[@]}"; do
  L1_TOTAL=$((L1_TOTAL + 1))
  if bash -n "$f" 2>/dev/null; then
    pass "syntax $(basename "$f")"
    L1_PASS=$((L1_PASS + 1))
  else
    fail "syntax $(basename "$f")"
  fi
done
echo "  Layer 1: $L1_PASS/$L1_TOTAL"

# ── Layer 2: Interface Contract (--help exits 0) ─────────────────────
echo ""
echo "═══ Layer 2: Interface Contract (--help) ═══"
L2_PASS=0; L2_TOTAL=0
for f in "${ALL_SCRIPTS[@]}"; do
  L2_TOTAL=$((L2_TOTAL + 1))
  if bash "$f" --help >/dev/null 2>&1; then
    pass "--help $(basename "$f")"
    L2_PASS=$((L2_PASS + 1))
  else
    fail "--help $(basename "$f")"
  fi
done
echo "  Layer 2: $L2_PASS/$L2_TOTAL"

# ── Layer 3: Error Handling (missing args → non-zero) ────────────────
echo ""
echo "═══ Layer 3: Error Handling (missing args) ═══"
L3_PASS=0; L3_TOTAL=0
for f in "${REQUIRED_ARG_SCRIPTS[@]}"; do
  L3_TOTAL=$((L3_TOTAL + 1))
  exit_code=0
  bash "$f" >/dev/null 2>&1 || exit_code=$?
  if [[ $exit_code -ne 0 ]]; then
    pass "no-args-error $(basename "$f") (exit $exit_code)"
    L3_PASS=$((L3_PASS + 1))
  else
    fail "no-args-error $(basename "$f") (should exit non-zero)"
  fi
done
echo "  Layer 3: $L3_PASS/$L3_TOTAL"

# ── Layer 4: Pattern Consistency (structural grep) ───────────────────
echo ""
echo "═══ Layer 4: Pattern Consistency ═══"
L4_PASS=0; L4_TOTAL=0

check_pattern() {
  local label="$1" pattern="$2" expected="$3"
  L4_TOTAL=$((L4_TOTAL + 1))
  local count
  count=$(grep -l "$pattern" "${ALL_SCRIPTS[@]}" 2>/dev/null | wc -l | tr -d ' ')
  if [[ "$count" -ge "$expected" ]]; then
    pass "$label ($count/$expected)"
    L4_PASS=$((L4_PASS + 1))
  else
    fail "$label ($count/$expected)"
  fi
}

check_pattern "set -euo pipefail"    "set -euo pipefail"    10
check_pattern "show_help()"          "show_help()"          10
check_pattern "--help) show_help"    "\-\-help) show_help"  10
check_pattern "--json option"        "\-\-json"              9
check_pattern "shebang env bash"     "#!/usr/bin/env bash"  10
check_pattern "shift in case"        "shift"                10

# gh auth check — only in pr-creation scripts
L4_TOTAL=$((L4_TOTAL + 1))
GH_AUTH_COUNT=$(grep -l "gh auth status" "${PR_LIFECYCLE_SCRIPTS[@]}" 2>/dev/null | wc -l | tr -d ' ')
if [[ "$GH_AUTH_COUNT" -ge 7 ]]; then
  pass "gh auth status in PR scripts ($GH_AUTH_COUNT/7)"
  L4_PASS=$((L4_PASS + 1))
else
  fail "gh auth status in PR scripts ($GH_AUTH_COUNT/7)"
fi

echo "  Layer 4: $L4_PASS/$L4_TOTAL"

# ── Layer 5: Documentation Integrity ─────────────────────────────────
echo ""
echo "═══ Layer 5: Documentation Integrity ═══"
L5_PASS=0; L5_TOTAL=0

# 5a: All script paths in CLAUDE.md exist and are executable
L5_TOTAL=$((L5_TOTAL + 1))
DOC_SCRIPTS=$(grep -oE '\.ctx/skills/[^ )`"]+\.sh' CLAUDE.md 2>/dev/null | sort -u)
DOC_MISSING=0
while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  if [[ ! -x "$f" ]]; then
    DOC_MISSING=$((DOC_MISSING + 1))
    echo "    missing/not-exec: $f"
  fi
done <<< "$DOC_SCRIPTS"
if [[ "$DOC_MISSING" -eq 0 ]]; then
  pass "CLAUDE.md script refs all exist"
  L5_PASS=$((L5_PASS + 1))
else
  fail "CLAUDE.md has $DOC_MISSING broken script refs"
fi

# 5b: AGENTS.md contains agent-browser
L5_TOTAL=$((L5_TOTAL + 1))
if grep -q "agent-browser" AGENTS.md 2>/dev/null; then
  pass "AGENTS.md lists agent-browser"
  L5_PASS=$((L5_PASS + 1))
else
  fail "AGENTS.md missing agent-browser"
fi

# 5c: pr-creation SKILL.md lists all 7 new scripts
L5_TOTAL=$((L5_TOTAL + 1))
NEW_SCRIPT_REFS=$(grep -c "scripts/\(pr-status\|pr-comments\|approval\|create-prs\|rerun-failed\|create-issue\|update-main\)" .ctx/skills/pr-creation/SKILL.md 2>/dev/null || echo 0)
if [[ "$NEW_SCRIPT_REFS" -ge 7 ]]; then
  pass "pr-creation SKILL.md lists all 7 new scripts ($NEW_SCRIPT_REFS refs)"
  L5_PASS=$((L5_PASS + 1))
else
  fail "pr-creation SKILL.md missing script refs ($NEW_SCRIPT_REFS/7)"
fi

# 5d: agent-browser SKILL.md references all 3 scripts
L5_TOTAL=$((L5_TOTAL + 1))
AB_REFS=$(grep -c "scripts/\(browse\|scrape\|interact\)" .ctx/skills/agent-browser/SKILL.md 2>/dev/null || echo 0)
if [[ "$AB_REFS" -ge 3 ]]; then
  pass "agent-browser SKILL.md lists all 3 scripts ($AB_REFS refs)"
  L5_PASS=$((L5_PASS + 1))
else
  fail "agent-browser SKILL.md missing script refs ($AB_REFS/3)"
fi

# 5e: CLAUDE.md has new Common Tasks entries
L5_TOTAL=$((L5_TOTAL + 1))
NEW_TASKS=$(grep -c "pr-status\|pr-comments\|approval\|create-prs\|rerun-failed\|create-issue\|update-main\|browse\.sh\|scrape\.sh\|interact\.sh" CLAUDE.md 2>/dev/null || echo 0)
if [[ "$NEW_TASKS" -ge 10 ]]; then
  pass "CLAUDE.md has $NEW_TASKS new Common Tasks entries"
  L5_PASS=$((L5_PASS + 1))
else
  fail "CLAUDE.md missing new entries ($NEW_TASKS/10)"
fi

echo "  Layer 5: $L5_PASS/$L5_TOTAL"

# ── Layer 6: Executable Permissions ──────────────────────────────────
echo ""
echo "═══ Layer 6: Executable Permissions ═══"
L6_PASS=0; L6_TOTAL=1
NON_EXEC=$(find .ctx/skills/agent-browser/scripts .ctx/skills/pr-creation/scripts -name "*.sh" ! -perm -u+x 2>/dev/null | wc -l | tr -d ' ')
if [[ "$NON_EXEC" -eq 0 ]]; then
  pass "all .sh files are executable"
  L6_PASS=1
else
  fail "$NON_EXEC scripts missing +x"
fi
echo "  Layer 6: $L6_PASS/$L6_TOTAL"

# ── Scorecard ─────────────────────────────────────────────────────────
echo ""
echo "╔═══════════════════════════════════════╗"
echo "║         VALIDATION SCORECARD          ║"
echo "╠═══════════════════════════════════════╣"
printf "║  Layer 1: Syntax         %2d/%-2d       ║\n" "$L1_PASS" "$L1_TOTAL"
printf "║  Layer 2: Interface      %2d/%-2d       ║\n" "$L2_PASS" "$L2_TOTAL"
printf "║  Layer 3: Error handling  %1d/%-1d        ║\n" "$L3_PASS" "$L3_TOTAL"
printf "║  Layer 4: Patterns        %1d/%-1d        ║\n" "$L4_PASS" "$L4_TOTAL"
printf "║  Layer 5: Docs            %1d/%-1d        ║\n" "$L5_PASS" "$L5_TOTAL"
printf "║  Layer 6: Permissions     %1d/%-1d        ║\n" "$L6_PASS" "$L6_TOTAL"
echo "╠═══════════════════════════════════════╣"
printf "║  TOTAL: %2d / %-2d                      ║\n" "$PASSED" "$TOTAL"
echo "╚═══════════════════════════════════════╝"

if [[ "$PASSED" -eq "$TOTAL" ]]; then
  echo ""
  echo "ALL CHECKS PASSED"
  exit 0
else
  echo ""
  echo "FAILURES (${#FAILED_DETAILS[@]}):"
  for d in "${FAILED_DETAILS[@]}"; do
    echo "  - $d"
  done
  exit 1
fi
