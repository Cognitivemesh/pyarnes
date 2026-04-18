#!/usr/bin/env bash
# Smoke-test the Copier template against the current working tree.
#
# Renders the template into a scratch directory with default answers,
# asserts the expected structure (src/<module>/__init__.py exists; no
# packages/ or tests/ directories leaked through), and reports back.
#
# Use this before tagging a release, or after editing anything under
# template/ or copier.yml.
#
# Note on `.copier-answers.yml`: Copier only writes that file when the
# source is a clean git ref. Running this script against an uncommitted
# working tree therefore skips the answers file. That is expected and
# harmless for structural checks. The full round-trip (uv sync from git
# URLs + copier update) requires the changes to be pushed to the
# github.com/Cognitivemesh/pyarnes repo first.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEST="${1:-/tmp/pyarnes-smoke}"
PROJECT_NAME="${PROJECT_NAME:-pyarnes-smoke}"
PROJECT_DESCRIPTION="${PROJECT_DESCRIPTION:-Smoke-test project}"
PROJECT_MODULE="${PROJECT_NAME//-/_}"

echo "━━━ pyarnes template smoke test ━━━"
echo "  source:  ${REPO_ROOT}"
echo "  dest:    ${DEST}"
echo "  project: ${PROJECT_NAME}"
echo

rm -rf "${DEST}"

# Render the template with defaults, no prompts.
uvx copier copy \
  --defaults \
  --data "project_name=${PROJECT_NAME}" \
  --data "project_description=${PROJECT_DESCRIPTION}" \
  "${REPO_ROOT}" \
  "${DEST}"

echo
echo "━━━ Structural assertions ━━━"

fail=0
assert_exists() {
  if [[ -e "${DEST}/$1" ]]; then
    echo "  ok     ${1}"
  else
    echo "  FAIL   missing: ${1}"
    fail=1
  fi
}
assert_absent() {
  if [[ ! -e "${DEST}/$1" ]]; then
    echo "  ok     (absent) ${1}"
  else
    echo "  FAIL   unexpected: ${1}"
    fail=1
  fi
}

assert_exists "pyproject.toml"
assert_exists "README.md"
assert_exists "CLAUDE.md"
assert_exists "LICENSE"
assert_exists "mkdocs.yml"
assert_exists ".python-version"
assert_exists ".gitignore"
assert_exists ".markdownlint.yaml"
assert_exists ".yamllint.yaml"
assert_exists "src/${PROJECT_MODULE}/__init__.py"
assert_exists "docs/index.md"
assert_exists "docs/getting-started/installation.md"
assert_exists "docs/getting-started/quickstart.md"
assert_exists "docs/development/tasks.md"
assert_exists ".claude/skills/python-test/SKILL.md"

# Must NOT be present in the generated tree.
assert_absent "packages"
assert_absent "tests"
assert_absent "specs"
assert_absent "template"
assert_absent "copier.yml"

# Spot-check the rendered pyproject for the five git-URL deps.
# Loose regex so whitespace variations (`pkg@git+…` vs `pkg @ git+…`) still match.
echo
echo "━━━ pyproject.toml content check ━━━"
for pkg in core harness guardrails bench tasks; do
  if grep -qE "pyarnes-${pkg}\s*@\s*git\+https.*#subdirectory=packages/${pkg}" "${DEST}/pyproject.toml"; then
    echo "  ok     pyarnes-${pkg} git URL present"
  else
    echo "  FAIL   pyarnes-${pkg} git URL missing from pyproject.toml"
    fail=1
  fi
done

if grep -qE '^\s*authors\s*=' "${DEST}/pyproject.toml"; then
  echo "  FAIL   pyproject.toml should not define an 'authors' field"
  fail=1
else
  echo "  ok     (absent) 'authors = …' field"
fi

echo
if [[ ${fail} -ne 0 ]]; then
  echo "━━━ SMOKE TEST FAILED ━━━"
  exit 1
fi

echo "━━━ SMOKE TEST PASSED ━━━"
echo
echo "Next steps (require pushed commits on github.com/Cognitivemesh/pyarnes):"
echo "  cd ${DEST}"
echo "  uv sync"
echo "  uv run tasks check"
