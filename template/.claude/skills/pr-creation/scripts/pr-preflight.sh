#!/usr/bin/env bash
set -euo pipefail

# pr-preflight.sh — 3-tier pre-submission quality gate
#
# Mirrors the project's verification standard (specs/INDEX.md Appendix):
#   Tier 1 (--quick):  Dev gate — biome fix + typecheck
#   Tier 2 (default):  PR gate  — Tier 1 + biome check + quality-fit + CI
#   Tier 3 (--full):   Integration — Tier 2 + full repo validation
#
# On success, creates .pr-preflight-passed marker file for the guard hook.
#
# Usage: pr-preflight.sh [--quick] [--full] [--json]
#
# Exit codes:
#   0  All checks passed
#   1  One or more checks failed

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

TIER=2
JSON_OUTPUT=false

for arg in "$@"; do
  case "$arg" in
    --quick) TIER=1 ;;
    --full)  TIER=3 ;;
    --json)  JSON_OUTPUT=true ;;
    --help|-h)
      cat <<'USAGE'
Usage: pr-preflight.sh [--quick] [--full] [--json]

Tiers:
  --quick   Tier 1 (Dev Gate): biome fix + typecheck
  (default) Tier 2 (PR Gate):  Tier 1 + biome check + quality-fit + full CI
  --full    Tier 3 (Integration): Tier 2 + full repo validation (make ci)

Options:
  --json    Output results as JSON
  --help    Show this help

Examples:
  pr-preflight.sh              # Tier 2 — standard PR gate
  pr-preflight.sh --quick      # Tier 1 — fast dev feedback
  pr-preflight.sh --full       # Tier 3 — major/cross-cutting PRs
USAGE
      exit 0
      ;;
    *) echo "Unknown option: $arg"; exit 1 ;;
  esac
done

echo "═══════════════════════════════════════════════════════════"
echo "  PR Pre-Flight Quality Gate"
echo "  Tier: $TIER"
echo "  Branch: $(git branch --show-current 2>/dev/null || echo 'detached')"
echo "═══════════════════════════════════════════════════════════"
echo ""

PASS=0
FAIL=0
FAILED_CHECKS=""
RESULTS_JSON="["

run_check() {
  local name="$1"
  shift
  echo -n "  [$name] ... "
  if "$@" &>/dev/null; then
    echo "PASS"
    PASS=$((PASS + 1))
    RESULTS_JSON="${RESULTS_JSON}{\"name\":\"$name\",\"result\":\"PASS\"},"
  else
    echo "FAIL"
    FAIL=$((FAIL + 1))
    FAILED_CHECKS="${FAILED_CHECKS}  - ${name}\n"
    RESULTS_JSON="${RESULTS_JSON}{\"name\":\"$name\",\"result\":\"FAIL\"},"
  fi
}

# ─── Tier 1: Dev Gate ─────────────────────────────────────
run_check "biome-fix"  bunx biome check --write .
run_check "typecheck"  make toolbox-typecheck-native

# ─── Tier 2: PR Gate ──────────────────────────────────────
# Note: toolbox-ci-all includes install → build → check → typecheck → tests.
# We run biome-check and quality-fit as separate visible steps before the full
# CI gate so failures are immediately attributable to a specific check.
if [ "$TIER" -ge 2 ]; then
  run_check "biome-check"   make toolbox-check
  run_check "quality-fit (advisory)"  bun run quality:self-diagnose
  run_check "ci-gate"       make toolbox-ci-all
fi

# ─── Tier 3: Integration Gate ─────────────────────────────
if [ "$TIER" -ge 3 ]; then
  run_check "full-repo"    make ci
fi

# ─── Results ──────────────────────────────────────────────
echo ""
echo "───────────────────────────────────────────────────────────"

VERDICT="PASS"
if [ "$FAIL" -gt 0 ]; then
  VERDICT="FAIL"
fi

echo "  Tier $TIER: $PASS passed, $FAIL failed — $VERDICT"

if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "  Failed checks:"
  echo -e "$FAILED_CHECKS"
fi

echo "═══════════════════════════════════════════════════════════"

# ─── Marker file for guard hook ───────────────────────────
MARKER_FILE="$REPO_ROOT/.pr-preflight-passed"
if [ "$VERDICT" = "PASS" ]; then
  date -Iseconds > "$MARKER_FILE"
  echo ""
  echo "Marker written: $MARKER_FILE"
else
  rm -f "$MARKER_FILE"
fi

# ─── JSON output ──────────────────────────────────────────
if [ "$JSON_OUTPUT" = true ]; then
  # Remove trailing comma from results array
  RESULTS_JSON="${RESULTS_JSON%,}]"
  cat <<JSON
{"tier":$TIER,"steps":$RESULTS_JSON,"verdict":"$VERDICT"}
JSON
fi

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
exit 0
