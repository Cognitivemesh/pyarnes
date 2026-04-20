---
name: python-test
description: Scaffold pytest tests (unit or BDD) for this pyarnes-based project. Use when the user asks to "write a test", "add a test", "test this function/class/module", "scaffold tests", or asks how to start testing. The skill creates tests/ on first use, follows pyarnes conventions (async-first, Red → Green → Refactor, loguru stderr logging in tests), and integrates with hypothesis + pytest-bdd when appropriate.
---

# python-test — scaffold tests following pyarnes conventions

This skill handles the **first-test problem**: a pyarnes-template project ships with pytest installed but **no `tests/` directory**. Activate it whenever the developer asks for a test.

## When this skill activates

Typical user phrasings:

- "Write a test for `Greeter`"
- "Add a unit test for the `parse_config` function"
- "Scaffold tests for this project"
- "I want to test `ReadFileTool`"
- "Write a BDD feature for the agent loop"
- "How do I start testing here?"

## What the skill does

### 1. Bootstrap the tests tree if missing

On first use, create:

```
tests/
├── __init__.py          # "" empty
├── conftest.py          # configures loguru for test runs
└── unit/
    ├── __init__.py      # ""
    └── test_<target>.py # the first test
```

For BDD requests, also create:

```
tests/features/
├── __init__.py
├── <feature>.feature
└── steps/
    ├── __init__.py
    └── test_<feature>_steps.py
```

### 2. `tests/conftest.py` template

If `tests/conftest.py` does not exist, create it with:

```python
"""Shared pytest fixtures and configuration."""

from __future__ import annotations

from pyarnes_core.observe.logger import configure_logging


def pytest_configure() -> None:
    """Configure structured logging for test runs (human-readable)."""
    configure_logging(level="DEBUG", json=False)


__all__ = ["configure_logging"]
```

### 3. Unit-test skeleton

For a target class/function `<Target>` living in `src/<project_module>/<module>.py`, write `tests/unit/test_<module>.py` following this shape:

```python
"""Tests for <module>.<Target>."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from <project_module>.<module> import <Target>


# ── Helpers / fixtures ─────────────────────────────────────────────────────

# Put small test doubles (fakes, scripted models, echo tools) here using
# @dataclass so they're readable. Mirror the shape of FakeModel / EchoTool in
# the pyarnes repo if you're testing loop- or tool-adjacent behaviour.


# ── Tests ──────────────────────────────────────────────────────────────────


class Test<Target>:
    """<Target> does <one-line behaviour summary>."""

    async def test_<behaviour>(self) -> None:
        # Arrange
        ...
        # Act
        ...
        # Assert
        assert ...
```

Conventions to enforce:

- **Async-first**: use `async def test_…` and `await` — pytest-asyncio is configured in `asyncio_mode = "auto"`.
- **Arrange → Act → Assert** comment markers in each test.
- **One behaviour per test** — name tests after the behaviour, not the method.
- **Group related tests** in a `class Test<Target>` (or a module-level docstring if very short).
- **Prefer `@dataclass` fakes** over `unittest.mock.Mock` — they read like documentation.
- **Use `hypothesis`** (`@given(…)`) for property-based tests when the input space is wide.
- **Import target from `<project_module>.…`** using the configured module name.

### 4. BDD scaffold

For `tests/features/<feature>.feature`:

```gherkin
Feature: <feature name>
  As a <role>
  I want <goal>
  So that <outcome>

  Scenario: <behaviour>
    Given <precondition>
    When <action>
    Then <expected outcome>
```

For `tests/features/steps/test_<feature>_steps.py`:

```python
"""Step definitions for <feature>.feature."""

from __future__ import annotations

from pytest_bdd import given, scenarios, then, when

scenarios("../<feature>.feature")


@given(...)
def _given_...() -> None:
    ...


@when(...)
def _when_...() -> None:
    ...


@then(...)
def _then_...() -> None:
    assert ...
```

### 5. After scaffolding

Tell the developer:

- Run `uv run tasks test` to execute the new test. It will **fail** — that's the Red step of TDD.
- Implement the minimum production code in `src/<project_module>/…` to make it pass (Green).
- Refactor with tests green.
- Keep the watch mode running in another terminal: `uv run tasks watch`.

## Patterns worth mirroring

When the developer is writing harness-adjacent tests, follow the patterns used in the pyarnes repo:

- Agent-loop tests: small scripted `FakeModel` returning an action list, a handful of `ToolHandler` implementations (`EchoTool`, `FailingTool`), and `LoopConfig(max_iterations=…, max_retries=…)` kept low for speed.
- Guardrail tests: parametrize over allowed and disallowed inputs, expect `UserFixableError` on violations.
- Error-taxonomy tests: `with pytest.raises(TransientError): …`, verifying retry behaviour from pyarnes-core.
- Lifecycle tests: drive a `Lifecycle` through `Phase` transitions and assert the full transition history.

## Security patterns for path-validation tests

When the target under test performs **path containment checks** (guardrail, file-access
tool, sandbox validator), always include these two regression tests. Both were confirmed
HIGH-severity vulnerabilities caused by the `PurePosixPath + startswith` anti-pattern:

| Attack | Payload | Why it bypasses `startswith("/workspace")` |
|--------|---------|-------------------------------------------|
| `..` traversal | `/workspace/../etc/passwd` | `PurePosixPath` is lexical — does NOT resolve `..` |
| Sibling prefix | `/workspace2/secret` | String prefix matches without a path boundary |

Correct implementation uses `Path.resolve()` + `is_relative_to()`:

```python
resolved = Path(value).resolve()  # OS canonicalization — collapses '..' and symlinks
if not any(resolved.is_relative_to(root) for root in allowed_roots):
    raise UserFixableError(...)
```

Mandatory test pair — add to every path-guard test class:

```python
def test_dot_dot_traversal_blocked(self) -> None:
    g = <GuardClass>(allowed_roots=("/workspace",))
    with pytest.raises(UserFixableError, match="outside allowed roots"):
        g.check("read_file", {"path": "/workspace/../etc/passwd"})

def test_sibling_prefix_blocked(self) -> None:
    g = <GuardClass>(allowed_roots=("/workspace",))
    with pytest.raises(UserFixableError, match="outside allowed roots"):
        g.check("read_file", {"path": "/workspace2/secret.txt"})
```

A test suite that only checks "allowed path passes" and "unrelated path fails" will miss
both attacks. These tests must be RED before the fix and GREEN after.

## What the skill does NOT do

- It does not rewrite existing tests. If `tests/unit/test_<target>.py` exists, add a new test there or propose a new file.
- It does not add dependencies. Everything needed (pytest, pytest-asyncio, pytest-bdd, hypothesis) is already in the dev-deps group.
- It does not run the tests itself — it produces the files and tells the developer the next command.
