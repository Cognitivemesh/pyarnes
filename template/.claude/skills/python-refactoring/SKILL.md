---
name: python-refactoring
description: Behavior-preserving Python refactoring for pyarnes-based projects. Use when the user asks to "refactor X", "extract X into an atom/molecule/port/adapter", "introduce a seam for X", "move X to the <domain> folder", "strangle X", "inline X", or "rename-to-domain". Complements the `python-test` skill: `python-test` drives new behavior via Red/Green/Refactor, `python-refactoring` restructures code whose behavior is already covered by tests. Enforces atoms/molecules/systems layering, DDD folder placement, and hexagonal (ports & adapters) boundaries.
---

# python-refactoring — behavior-preserving moves with a test safety net

This skill handles the **second problem**: once behavior is covered by
`python-test`, how do we restructure the implementation without breaking
it? Activate it whenever the developer asks to move, extract, inline, or
rename code — not to add new behavior.

Pair with `python-test`:
- `python-test` → new behavior, failing test first (Red → Green).
- `python-refactoring` → keep behavior, change shape (tests stay green).

## When this skill activates

Typical user phrasings:

- "Refactor `PathGuardrail.check`"
- "Extract `canonicalize` as an atom"
- "Compose these two atoms into a molecule"
- "Introduce a port for the logger"
- "Move this under `safety/`"
- "Strangle the old loop by extracting `retry_policy`"
- "Inline this one-use helper"
- "Rename-to-domain: move `guardrails.py` into `safety/`"

Do **not** activate for:
- Brand-new features or bug fixes that change behavior — use
  `python-test` first to lock the behavior in, then this skill.
- Pure formatting or rename-only edits — use the editor's rename; the
  skill's overhead isn't worth it.

## Pre-flight checks (skill refuses to proceed otherwise)

1. `uv run tasks check` is green on the current branch. Refactoring on
   a red baseline is banned — there is no safety net.
2. `git status` is clean, or contains only the in-progress diff the
   user explicitly mentions. Unknown untracked files pause the skill.
3. The target code has tests. Run `uv run tasks test -k <target>` and
   confirm at least one test exercises the code being moved. If not,
   stop and recommend `python-test` first.

## The refactor catalog

Each move has a fixed shape and checklist. Pick exactly one per commit.

### Layout convention

Files live **flat under the domain folder** (no `atoms/` or
`molecules/` subdirectories). The composability layer is stated in
each module's opening docstring line (e.g. `"""Atom: X — …"""` or
`"""Molecule: Y — …"""`) and in the domain's `__init__.py` overview.

### Extract atom

Pull a pure function out of a class method or long function.

- Precondition: the extracted logic has no I/O and no hidden state.
- Target path: `packages/<pkg>/src/<module>/<domain>/<name>.py`.
- Open the module with a docstring starting `"""Atom: <concept> — …"""`.
- Write `tests/unit/<domain>/test_<name>.py` **before** the extraction.
  The test asserts the contract the new function will satisfy.
- Replace the original code with a call to the new atom. Run tests.
- Forbidden imports from an atom: anything under `adapters/`, any
  third-party I/O library (loguru, requests, pathlib operations that
  touch the FS, etc. — path-string parsing is fine).

### Extract molecule

Compose two or more atoms (or one atom + a port) into a named helper.

- Target path: `packages/<pkg>/src/<module>/<domain>/<name>.py`
  (same folder as the atoms it composes).
- Open the module with a docstring starting `"""Molecule: <concept> — …"""`.
- Allowed imports: own domain's atoms, own domain's `ports.py`, other
  domains' atoms. **Not** other domains' molecules (prevents cycles).
- Mirror test at `tests/unit/<domain>/test_<name>.py`.

### Extract port

Replace a concrete dependency with a Protocol parameter.

- Add the Protocol to `packages/<pkg>/src/<module>/<domain>/ports.py`.
- The port file may import only from `typing` and the domain's own
  value objects. No implementations.
- Default the constructor parameter to the existing concrete class so
  callers see no behavior change.
- Add a fake implementation in the test file to prove the seam works.

### Extract adapter

Move I/O code behind an existing port.

- Target path:
  `packages/<pkg>/src/<module>/<domain>/adapters/<name>.py`.
- Adapter imports the port; the domain imports only the port.
- Inject the adapter at the system edge (top-level `AgentLoop`,
  `GuardrailChain`, etc.) — not inside atoms/molecules.

### Inline

Reverse of extract, when a helper has exactly one caller and no test
of its own that would be lost.

- Delete the helper file and its test file.
- Inline the body at the call site. Run tests.

### Rename-to-domain

Move a module from a technical layer (`utils.py`, `helpers.py`) or
legacy location into its DDD domain folder.

- Create the new path under `<domain>/{atoms,molecules}/`.
- Leave a one-line stub at the old path for one release cycle:
  `from <new.path> import *  # noqa: F401,F403`.
- Open a follow-up note to remove the stub in the next minor version.
- No behavior change — public API is preserved via the stub.

## Safety rules (apply to every move)

- Public signatures change only by **widening** — add keyword-only
  parameters with defaults. Narrowing or reordering requires a
  deprecation cycle, and that is a feature change, not a refactor.
- Tests run green **before** and **after** the move. If a test fails
  during the move, revert immediately — the move is wrong.
- One move per commit. If you find yourself doing two, split the
  commit.
- No drive-by cleanup. Adjacent code, comments, and formatting are
  out of scope unless the move directly orphans them.
- If the move would orphan imports, variables, or helpers in the
  original file, remove them in the **same** commit — leaving dead
  code behind is not behavior-preserving from the reader's viewpoint.

## Commit discipline

Commit title prefix: `refactor(<domain>): <move> <target>`

Examples:
- `refactor(safety): extract atom canonicalize`
- `refactor(observability): extract port LogSink`
- `refactor(dispatch): rename-to-domain loop.retry → dispatch/atoms/retry_policy`

Commit body template:

```
Move: <extract-atom | extract-molecule | extract-port | extract-adapter
       | inline | rename-to-domain>
From: packages/<pkg>/src/<old-path>
To:   packages/<pkg>/src/<new-path>
No behavior change — verified by tests/unit/<domain>/test_<name>.py
```

## Hexagonal check before closing the skill

Run these greps on the touched domain and refuse to close if any hit:

- `grep -rn 'import loguru' packages/<pkg>/src/<module>/<domain>/` for
  files whose docstring starts with `"""Atom:` → atoms must not import
  loguru. (Grep the domain folder flat; there are no `atoms/` /
  `molecules/` subfolders.)
- `grep -rn 'from \.adapters' packages/<pkg>/src/<module>/<domain>/`
  for files whose docstring starts with `"""Molecule:` → molecules
  must not import adapters.
- `grep -rn 'open(' packages/<pkg>/src/<module>/<domain>/` for files
  whose docstring starts with `"""Atom:` → atoms must not open files.

Run `uv run tasks radon:cc` — cyclomatic complexity of each new atom
should be ≤ 5. If higher, the "atom" is actually a molecule and lives
under `molecules/`.

Run `uv run tasks vulture` — catch any helper orphaned by the move.

## Exit criteria

- `uv run tasks check` is green.
- Every changed line traces to the single stated move.
- The commit message matches the template above.
- Diff is under ~300 lines. Larger diffs mean the move wasn't atomic;
  split into smaller moves.

## Integration with `python-test` and `tdd`

Full workflow when addressing a bug in this codebase:

1. `python-test` → write a failing test for the bug behavior (Red).
2. Minimum fix in the current shape (Green).
3. `python-refactoring` → extract atoms/molecules, introduce ports,
   move to the target DDD folder. Tests stay green throughout.
4. `uv run tasks check`. Commit each move independently.

The skills are idempotent — invoking `python-refactoring` on code that
is already well-factored results in a no-op and a short "nothing to
do" response.

## What the skill does NOT do

- It does not add tests. If coverage is missing, stop and invoke
  `python-test`.
- It does not change behavior. If the desired change is a bug fix or
  a feature, invoke `python-test` first.
- It does not delete pre-existing dead code not caused by the move.
  Mention it to the developer instead.
- It does not introduce speculative abstractions. A port is added
  only when there is a concrete second implementation (real + fake in
  a test counts as two) on the same commit or the immediately
  following one.
