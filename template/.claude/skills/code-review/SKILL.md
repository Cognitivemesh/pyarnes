---
name: code-review
description: |
  Security-focused and quality-focused code review for pyarnes-based projects.
  Checks for path-traversal anti-patterns, dangerous dynamic execution, test
  coverage gaps, and deviations from pyarnes conventions. Use when the user
  asks to "review this", "check my code", "security review", or "what did I miss".
license: Apache-2.0
metadata:
  author: cognitivemesh.org
  version: "1.0.0"
  execution_policy: on_demand
  priority: normal
  allowed-tools:
    - Bash(git:*)
    - Bash(uv:*)
    - Read
    - Grep
    - Glob
  triggers:
    - "review this"
    - "check my code"
    - "security review"
    - "what did I miss"
    - "code review"
    - "review changes"
    - "review PR"
---

# code-review — security and quality review

Performs a focused review of staged or recent changes. Checks security
regressions, test gaps, and pyarnes convention deviations.

## When this skill activates

- "Review this function"
- "Run a security review on my changes"
- "Check what I changed before I push"
- "Review my PR"

## What the skill does

### 1. Collect diff

```bash
git diff HEAD          # staged + unstaged changes
git diff origin/main   # full branch diff for PR review
```

### 2. Security checks

**Path containment** — any new code that checks whether a path is under a
root directory:

| Anti-pattern | Risk | Fix |
|---|---|---|
| `str.startswith("/workspace")` | `..` traversal + sibling prefix bypass | Use `Path.resolve() + is_relative_to()` |
| `PurePosixPath(x).parts` comparison | Lexical, does not resolve symlinks | Same fix |

**Dynamic execution** — flag any new use of:

```
eval, exec, compile, __import__, os.system, os.popen,
subprocess.Popen, subprocess.run, subprocess.call
```

These are prohibited without an explicit security comment explaining why the
call is safe. Use `pyarnes_core.safety.scan_code_arguments` to enforce this
at runtime for tools that accept code strings.

**Import safety** — `ctypes`, `subprocess`, `importlib` imports in tool
handlers need justification. In test helpers they are sometimes acceptable.

### 3. Test coverage gaps

For every new public function or class added, verify:

- [ ] A `TestXxx` class exists in `tests/unit/test_<module>.py`
- [ ] At least one test for the happy path
- [ ] At least one test for an error/edge case
- [ ] If the function takes path arguments: `test_dot_dot_traversal_blocked`
      and `test_sibling_prefix_blocked` both exist (see
      `python-test` skill for the mandatory test pair)

### 4. pyarnes convention checks

| Check | Where to look |
|---|---|
| New public symbol in `__all__` | Package `__init__.py` |
| Async-first (`async def`) | Tool handlers, loop callbacks |
| `loguru` logger, not `print` | Production code |
| `@dataclass` fakes, not `Mock` | Test helpers |
| Error type matches taxonomy | `TransientError` / `LLMRecoverableError` / `UserFixableError` |

### 5. Run the quality gate

```bash
uv run tasks check     # lint + typecheck + test
uv run tasks security  # bandit scan
```

Both must pass before the review is complete.

## After the review

Report findings grouped by severity:

- **HIGH**: Exploitable security issue (path traversal, RCE, auth bypass)
- **MEDIUM**: Policy violation (missing test, wrong error type, undeclared export)
- **LOW**: Style deviation (logging, naming)

For HIGH findings, provide the exact fix (not just the diagnosis).
