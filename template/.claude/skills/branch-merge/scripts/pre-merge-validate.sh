#!/usr/bin/env bash
set -euo pipefail

# pre-merge-validate.sh — Deterministic pre-merge CI validation
# Mirrors the canonical CI gate (ci.yml) to catch failures before push.
#
# Usage: pre-merge-validate.sh [--quick] [--browser]
#
# Modes:
#   (default)   Full CI gate: install → build → check → typecheck → tests
#                Equivalent to: make toolbox-ci-all
#   --quick     Fast gate: lint + typecheck only (for iterative work)
#   --browser   Include browser/render-parity tests (matches ci.yml exactly)
#
# Exit codes:
#   0  All checks passed
#   1  One or more hard failures (build, typecheck, test assertions)
#   2  Tests passed but coverage threshold missed
#   3  Lint/format issue (auto-fixable with biome --write)

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# Ensure bun is on PATH (may not be set when invoked from agent/hook contexts)
export PATH="$HOME/.bun/bin:$PATH"

MODE="full"
BROWSER_TESTS=false

for arg in "$@"; do
  case "$arg" in
    --quick) MODE="quick" ;;
    --browser) BROWSER_TESTS=true ;;
    *) echo "Unknown option: $arg"; exit 1 ;;
  esac
done

echo "═══════════════════════════════════════════════════════════"
echo "  Pre-Merge Validation"
echo "  Mode: $MODE$([ "$BROWSER_TESTS" = true ] && echo ' +browser' || true)"
echo "  CI parity: ci.yml → make toolbox-ci-all"
echo "═══════════════════════════════════════════════════════════"
echo ""

PASS=0
FAIL=0
FAILED_CHECKS=""
COVERAGE_FAIL=false
LINT_FAIL=false

run_check() {
  local name="$1"
  shift
  echo -n "  [$name] ... "
  local output=""
  if output="$("$@" 2>&1)"; then
    echo "PASS"
    PASS=$((PASS + 1))
  else
    # Detect lint/format issues
    if [ "$name" = "check" ]; then
      echo "FAIL (lint/format)"
      FAIL=$((FAIL + 1))
      FAILED_CHECKS="${FAILED_CHECKS}  - ${name} (lint/format)\n"
      LINT_FAIL=true
      return
    fi
    echo "FAIL"
    FAIL=$((FAIL + 1))
    FAILED_CHECKS="${FAILED_CHECKS}  - ${name}\n"
  fi
}

# Check coverage thresholds from coverage-summary.json (written by vitest's
# json-summary reporter). This replaces vitest's built-in threshold check,
# which previously caused vitest to exit non-zero on coverage miss — making
# the JSON test reporter write empty results and preventing reliable
# distinction between "tests failed" and "coverage threshold missed."
#
# Coverage thresholds are intentionally removed from vitest.config.ts so that
# vitest's exit code reflects ONLY test results. This function checks
# thresholds structurally from the coverage summary JSON.
check_coverage_thresholds() {
  local summary_file="$REPO_ROOT/toolbox/coverage/coverage-summary.json"
  if [ ! -f "$summary_file" ]; then
    echo "  [coverage] ... SKIP (no coverage-summary.json)"
    return
  fi

  local lines statements branches functions
  lines="$(jq '.total.lines.pct // 0' "$summary_file" 2>/dev/null || echo "0")"
  statements="$(jq '.total.statements.pct // 0' "$summary_file" 2>/dev/null || echo "0")"
  branches="$(jq '.total.branches.pct // 0' "$summary_file" 2>/dev/null || echo "0")"
  functions="$(jq '.total.functions.pct // 0' "$summary_file" 2>/dev/null || echo "0")"

  # Thresholds match the values previously in vitest.config.ts
  local threshold_lines=55
  local threshold_statements=55
  local threshold_branches=45
  local threshold_functions=50

  local cov_ok=true
  local cov_details=""
  if [ "$(echo "$lines < $threshold_lines" | bc -l)" = "1" ]; then
    cov_ok=false
    cov_details="${cov_details}    lines: ${lines}% < ${threshold_lines}%\n"
  fi
  if [ "$(echo "$statements < $threshold_statements" | bc -l)" = "1" ]; then
    cov_ok=false
    cov_details="${cov_details}    statements: ${statements}% < ${threshold_statements}%\n"
  fi
  if [ "$(echo "$branches < $threshold_branches" | bc -l)" = "1" ]; then
    cov_ok=false
    cov_details="${cov_details}    branches: ${branches}% < ${threshold_branches}%\n"
  fi
  if [ "$(echo "$functions < $threshold_functions" | bc -l)" = "1" ]; then
    cov_ok=false
    cov_details="${cov_details}    functions: ${functions}% < ${threshold_functions}%\n"
  fi

  if [ "$cov_ok" = true ]; then
    echo "  [coverage] ... PASS"
    PASS=$((PASS + 1))
  else
    echo "  [coverage] ... FAIL (threshold)"
    echo -e "$cov_details"
    FAIL=$((FAIL + 1))
    FAILED_CHECKS="${FAILED_CHECKS}  - coverage (threshold)\n"
    COVERAGE_FAIL=true
  fi
}

# ─── Quick mode: fast feedback loop ───────────────────────
if [ "$MODE" = "quick" ]; then
  run_check "lint"      make toolbox-lint
  run_check "typecheck" make toolbox-typecheck-native

# ─── Full mode: mirrors ci.yml canonical gate ─────────────
else
  # Step 1: Install (matches ci.yml "Install dependencies")
  run_check "install"   make toolbox-install

  # Step 2: Build (part of toolbox-ci-all)
  run_check "build"     make toolbox-build

  # Step 3: Biome check — lint + format (matches ci.yml via toolbox-ci-all)
  run_check "check"     make toolbox-check

  # Step 4: TypeScript (matches ci.yml via toolbox-ci-all)
  run_check "typecheck" make toolbox-typecheck-native

  # Step 5: Tests (matches ci.yml via toolbox-ci-all)
  if [ "$BROWSER_TESTS" = true ]; then
    run_check "tests"   make TOOLBOX_RUN_BROWSER_TESTS=1 toolbox-tests
  else
    run_check "tests"   make toolbox-tests
  fi

  # Step 6: Coverage thresholds (checked from coverage-summary.json)
  # Separated from vitest so test exit code is unambiguous.
  check_coverage_thresholds
fi

# ─── Results ──────────────────────────────────────────────
echo ""
echo "───────────────────────────────────────────────────────────"
echo "  Results: $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "  Failed checks:"
  echo -e "$FAILED_CHECKS"
fi
echo "═══════════════════════════════════════════════════════════"

if [ "$FAIL" -gt 0 ]; then
  # Exit 2: only coverage threshold failures (tests themselves passed)
  if [ "$COVERAGE_FAIL" = true ] && [ "$LINT_FAIL" = false ] && [ "$FAIL" -eq 1 ]; then
    exit 2
  fi
  # Exit 3: only lint/format failures (auto-fixable)
  if [ "$LINT_FAIL" = true ] && [ "$COVERAGE_FAIL" = false ] && [ "$FAIL" -eq 1 ]; then
    exit 3
  fi
  # Exit 1: hard failures (build, typecheck, test assertions, or mixed)
  exit 1
fi
exit 0
