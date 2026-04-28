# pyarnes_swarm — Test Strategy

## The rule

**No implementation step starts until new tests for that module are written and confirmed RED.**

Old tests are deleted immediately after the Refactor step for that module. There is no parallel old + new test period. A green old test suite while new tests are RED is a false safety net — it means you are testing the wrong package.

## TDD cycle per module

The cycle is strictly **Red → Green → Refactor**:

1. **RED** — write tests for the new module. Run `uv run pytest tests/swarm/test_<module>.py -q`. All tests must fail (`ImportError` or `AssertionError`). Confirm before touching implementation.

2. **GREEN** — write the minimum implementation to make tests pass. No polish. Ugly is fine. The goal is passing tests, not clean code.

3. **Round 1 review** — with tests green, verify that each test is testing the right thing (not just "it doesn't crash"). Identify missing happy-path coverage and add tests.

4. **Round 2 review** — add edge-case and error-path tests. Confirm error types are tested explicitly (e.g. `TransientError` on rate limit, `UserFixableError` on guardrail violation).

5. **REFACTOR** — with all tests green, clean up the implementation:
   - Remove duplication
   - Improve names
   - Enforce layer boundaries (no imports from lower layers)
   - Extract private helpers where logic is reused
   - Tests must stay **green throughout the refactor**. If any test goes red during refactor, the refactor broke behaviour — fix it before continuing.

6. **Delete old tests** — immediately after refactor. No old test file survives if the new test suite covers its intent. Run the full suite to confirm nothing regressed: `uv run pytest tests/swarm/ -q`.

## What "covers its intent" means

An old test is redundant if a new test:
- Tests the same public method / behaviour
- With the same or stricter inputs
- And the same or more specific assertions

An old test is NOT redundant if it tests:
- A behaviour the new tests don't cover
- An edge case that wasn't considered when writing the new tests

If an old test covers something new tests don't — add a new test covering that behaviour, then delete the old test.

## Watch mode during development

```bash
uv run tasks watch   # alias for: uv run tasks tdd
```

pytest-watch reruns on every file save. Red → Green iterations are visible immediately.

## Test organisation

```
tests/
└── swarm/
    ├── conftest.py           # shared fixtures (InMemoryBus, mock ModelClient, etc.)
    ├── test_ports.py
    ├── test_errors.py
    ├── test_budget.py
    ├── test_context.py
    ├── test_agent.py         # includes MessageCompactor
    ├── test_tools.py
    ├── test_verification.py
    ├── test_routing.py       # RuleBasedRouter + LLMCostRouter
    ├── test_bus.py           # InMemoryBus + TursoMessageBus (in-memory db_path)
    ├── test_guardrails.py
    ├── test_safety.py
    ├── test_observability.py
    ├── test_swarm.py         # Swarm + AgentSpec integration
    ├── test_compaction.py
    ├── test_secrets.py
    ├── test_providers.py
    ├── test_bench_scorers.py # ScoreResult + all scorer classes
    └── test_bench_eval.py    # EvalSuite.run() + cost_efficiency
```

## Test infrastructure

### Minimal fixtures (in `conftest.py`)

```python
import pytest
from pyarnes_swarm.bus import InMemoryBus
from pyarnes_swarm.ports import ModelClient

class StubModel(ModelClient):
    """Returns a canned final_answer for any input."""
    def __init__(self, content: str = "done") -> None:
        self.content = content

    async def next_action(self, messages: list[dict]) -> dict:
        return {"type": "final_answer", "content": self.content}

@pytest.fixture
def stub_model():
    return StubModel()

@pytest.fixture
def in_memory_bus():
    return InMemoryBus()
```

### No mocking of internal modules

Tests should use real implementations where possible. Mock only:
- `ModelClient` (avoids real LLM calls)
- `CostCalculator` (avoids real pricing API calls)
- OS keychain (`keyring`) — use `EnvSecretStore` in tests instead

### Async tests

All async tests use `pytest-asyncio`:

```python
import pytest

@pytest.mark.asyncio
async def test_agent_runs():
    ...
```

## Per-module test requirements

### `test_agent.py` must cover:
- `AgentLoop` runs to `final_answer`
- `AgentLoop` retries on `TransientError` up to `max_retries`
- `AgentLoop` returns `ToolMessage` on `LLMRecoverableError`
- `AgentLoop` stops on `UserFixableError`
- `MessageCompactor` passes through when below threshold
- `MessageCompactor` compacts when above threshold
- `MessageCompactor` always compacts when `context_window=None`

### `test_routing.py` must cover:
- `RuleBasedRouter` selects first matching rule
- `RuleBasedRouter` falls back to catch-all
- `LLMCostRouter` picks cheapest model within complexity tier
- `LLMCostRouter.observe()` updates weights (verify via next routing decision)

### `test_bus.py` must cover:
- `InMemoryBus` publish/subscribe in the same process
- `TursoMessageBus` publish/subscribe with `db_path=":memory:"`
- `resume_from` replays only messages after the given offset

### `test_secrets.py` must cover:
- `EnvSecretStore.get()` reads from `os.environ`
- `EnvSecretStore.get()` raises `KeyError` when key missing
- `ChainedSecretStore` tries first store; falls back to second
- `ChainedSecretStore` raises when all stores miss

### `test_bench_eval.py` must cover:
- `EvalSuite.run()` populates `EvalResult.usage` from `agent_usage + scorer_usage`
- `EvalSuite.run()` populates `EvalResult.cost` when `cost_calculator` is provided
- `EvalSuite.cost_efficiency` is `average_score / total_cost * 100`
- `EvalSuite.run()` with `ExactMatchScorer` returns `usage=None` (no scorer tokens)

## After Phase 2 is complete

All old tests under `tests/unit/`, `tests/features/`, and `tests/template/` are deleted. Only `tests/swarm/` remains.

Run the final check:
```bash
uv run tasks check   # lint + typecheck + test
uv run tasks vulture # no dead code
uv run tasks security # bandit clean
```
