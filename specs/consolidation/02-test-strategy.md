# pyarnes_swarm — Test Strategy (TDD Discipline)

> **Spec header**
>
> | Field | Value |
> |---|---|
> | **Title** | pyarnes_swarm — Test Strategy (TDD Discipline) |
> | **Status** | active |
> | **Type** | testing |
> | **Tags** | testing, strategy, tdd |
> | **Owns** | TDD cycle (RED → GREEN → REFACTOR per module), per-module test requirements, watch mode, test infrastructure fixtures, Phase 1 pitfalls |
> | **Depends on** | 01-package-structure.md, 07-swarm-api.md |
> | **Extends** | — |
> | **Supersedes** | — |
> | **Read after** | 01-package-structure.md |
> | **Read before** | 03-test-map.md |
> | **Not owned here** | test-to-module migration map (see `03-test-map.md`); dead-code audit policy (see `04-dead-code-audit.md`); tooling exclusions (see `17-tooling-artifacts.md`) |
> | **Last reviewed** | 2026-04-29 |

## Design Rationale

For every module, follow:

- [ ] Write a failing test (RED)
- [ ] Implement the simplest passing solution (GREEN)
- [ ] Refactor to clarity, keeping tests green (REFACTOR)
- [ ] Delete superseded tests once their intent is captured by the new surface

**Why delete old tests immediately after Refactor instead of keeping them as extra coverage?** Two test suites for the same module are not "extra safety" — they're conflicting specifications. When one passes and the other fails, you don't know which is correct. When both pass, you're paying maintenance cost for redundant tests. Deleting old tests after the new suite is green eliminates the ambiguity and forces the new tests to be complete rather than relying on the old ones as a safety net.

**Why confirm 100% RED before writing implementation?** If a test passes without implementation, it's testing nothing (the implementation it's supposed to test doesn't exist yet). A test that starts green proves it's not actually checking the target behaviour. `ImportError` or `AssertionError` on every new test is the required starting state.

**Why three review rounds (GREEN, Round 1, Round 2) before Refactor?** Tests written in the RED phase cover expected behaviour. Round 1 review catches happy-path gaps (the behaviour that will be called most often, but that you forgot to test because you were focused on the contract). Round 2 catches error paths (what happens when the model returns an unexpected format, when the budget is exhausted mid-call, when the bus is unreachable). Refactor only begins once both are covered — otherwise refactoring breaks untested behaviour.

## Specification

### The rule

**No implementation step starts until new tests for that module are written and confirmed RED.**

Old tests are deleted immediately after the Refactor step for that module. There is no parallel old + new test period. A green old test suite while new tests are RED is a false safety net — it means you are testing the wrong package.

### TDD cycle per module

The cycle is strictly **Red → Green → Refactor**:

1. **RED** — write tests for the new module or feature slice. Run `uv run pytest tests/swarm/test_<module>.py -q` for unit/integration coverage, or the owning `pytest-bdd` steps file under `tests/features/steps/` when the behavior is feature-level. All new coverage must fail (`ImportError` or `AssertionError`). Confirm before touching implementation.

2. **GREEN** — write the minimum implementation to make tests pass. No polish. Ugly is fine. The goal is passing tests, not clean code.

3. **Round 1 review** — with tests green, verify that each test is testing the right thing (not just "it doesn't crash"). Identify missing happy-path coverage and add tests.

4. **Round 2 review** — add edge-case and error-path tests. Confirm error types are tested explicitly (e.g. `TransientError` on rate limit, `UserFixableError` on guardrail violation).

5. **REFACTOR** — with all tests green, clean up the implementation:
   - Remove duplication
   - Improve names
   - Enforce layer boundaries (no imports from lower layers)
   - Extract private helpers where logic is reused
   - Tests must stay **green throughout the refactor**. If any test goes red during refactor, the refactor broke behaviour — fix it before continuing.

6. **Delete old runtime tests** — immediately after refactor. No old swarm-runtime test file survives if the new `tests/swarm/` or `tests/features/` coverage owns its intent. Template tests, tasks tests, and bench-specific tests that remain outside consolidation are kept in their own areas. Run the relevant suite to confirm nothing regressed: `uv run pytest tests/swarm/ tests/features/ -q`.

### What "covers its intent" means

An old test is redundant if a new test:
- Tests the same public method / behaviour
- With the same or stricter inputs
- And the same or more specific assertions

An old test is NOT redundant if it tests:
- A behaviour the new tests don't cover
- An edge case that wasn't considered when writing the new tests

If an old test covers something new tests don't — add a new test covering that behaviour, then delete the old test.

### Watch mode during development

```bash
uv run tasks watch   # alias for: uv run tasks tdd
```

pytest-watch reruns on every file save. Red → Green iterations are visible immediately.

### Test organisation

```sh
tests/
├── swarm/
│   ├── conftest.py           # shared fixtures (InMemoryBus, mock ModelClient, etc.)
│   ├── test_ports.py
│   ├── test_errors.py
│   ├── test_budget.py
│   ├── test_context.py
│   ├── test_agent.py         # includes MessageCompactor
│   ├── test_tools.py
│   ├── test_verification.py
│   ├── test_routing.py       # RuleBasedRouter + LLMCostRouter
│   ├── test_bus.py           # InMemoryBus + TursoMessageBus (in-memory db_path)
│   ├── test_guardrails.py
│   ├── test_safety.py
│   ├── test_observability.py
│   ├── test_swarm.py         # Swarm + AgentSpec integration
│   ├── test_compaction.py
│   ├── test_secrets.py
│   ├── test_providers.py
│   ├── test_bench_scorers.py # ScoreResult + all scorer classes
│   └── test_bench_eval.py    # EvalSuite.run() + cost_efficiency
└── features/
    ├── acceptance.feature          # end-to-end user-visible workflows
    ├── harness.feature             # loop/error-routing behavior contracts
    ├── feature_validation.feature  # observable runtime contracts (logging, retries, guardrails)
    ├── fact_evaluation.feature     # FACT high-level evaluator semantics
    ├── race_evaluation.feature     # RACE high-level evaluator semantics
    └── steps/
        ├── test_acceptance_steps.py
        ├── test_harness_steps.py
        ├── test_feature_validation_steps.py
        ├── test_fact_evaluation.py
        └── test_race_evaluation.py
```

### When To Promote A Test To A Feature

Not every migrated test should stay a unit test. Promote a legacy unit or
integration test into `tests/features/` when the behavior is easier to read as
a stable user-facing contract than as helper-level assertions.

Promote to a feature when the behavior:

- crosses more than one layer (`AgentLoop` + logger + guardrail + runtime wiring)
- is something an adopter would describe in plain Given/When/Then language
- produces an externally visible artifact or contract (JSONL, retry policy, lifecycle progression)
- is already best understood as a scenario, not as a pure function invariant

Keep it in `tests/swarm/` when the behavior is primarily a leaf concern:

- path parsing, walkers, scanners, and redactors
- retry math and other small deterministic helpers
- immutable value-object invariants
- parser / dedupe / normalization edge cases with many narrow inputs

The intended split for the current consolidation is:

- `harness.feature` owns loop error-taxonomy behavior that old `test_loop.py` expressed procedurally.
- `acceptance.feature` owns runtime and lifecycle flows that old `test_integration.py` and `test_runtime.py` covered indirectly.
- `feature_validation.feature` owns observable audit and validation contracts such as JSONL logging and guarded execution.
- `fact_evaluation.feature` and `race_evaluation.feature` own top-level evaluator semantics; helper-heavy extraction and normalization cases remain in bench unit tests.

### Test infrastructure

#### Minimal fixtures (in `conftest.py`)

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

#### No mocking of internal modules

Tests should use real implementations where possible. Mock only:
- `ModelClient` (avoids real LLM calls)
- `CostCalculator` (avoids real pricing API calls)
- OS keychain (`keyring`) — use `EnvSecretStore` in tests instead

#### Async tests

All async tests use `pytest-asyncio`:

```python
import pytest

@pytest.mark.asyncio
async def test_agent_runs():
    ...
```

### Per-module test requirements

Feature files must cover the behavior-level slices that are hard to see in
isolated unit tests:

- `acceptance.feature` must cover full-session workflows: tool call + final answer, lifecycle progression, and at least one guardrail-visible failure.
- `harness.feature` must cover the four-error taxonomy as scenarios, not only as helper assertions.
- `feature_validation.feature` must cover observable runtime artifacts such as ToolCallLogger JSONL shape and retry/guardrail integration in a full loop.
- `fact_evaluation.feature` and `race_evaluation.feature` must pin top-level scoring semantics that adopters care about, while low-level evaluator mechanics stay unit-tested in `bench/`.

#### `test_agent.py` must cover:
- [ ]`AgentLoop` runs to `final_answer` that matches the intent of the run.
- [ ]`AgentLoop` retries on `TransientError` up to `max_retries`
- [ ]`AgentLoop` returns `ToolMessage` on `LLMRecoverableError`
- [ ]`AgentLoop` stops on `UserFixableError`
- [ ]`MessageCompactor` passes through when below threshold
- [ ]`MessageCompactor` compacts when above threshold
- [ ]`MessageCompactor` always compacts when `context_window=None`

#### `test_routing.py` must cover:
- [ ]`RuleBasedRouter` selects first matching rule
- [ ]`RuleBasedRouter` falls back to catch-all
- [ ]`LLMCostRouter` picks cheapest model within complexity tier
- [ ]`LLMCostRouter.observe()` updates weights (verify via next routing decision)

#### `test_bus.py` must cover:
- [ ]`InMemoryBus` publish/subscribe in the same process
- [ ]`TursoMessageBus` publish/subscribe with `db_path=":memory:"`
- [ ]`resume_from` replays only messages after the given offset

#### `test_secrets.py` must cover:
- [ ]`EnvSecretStore.get()` reads from `os.environ`
- [ ]`EnvSecretStore.get()` raises `KeyError` when key missing
- [ ]`ChainedSecretStore` tries first store; falls back to second
- [ ]`ChainedSecretStore` raises when all stores miss

#### `test_bench_eval.py` must cover:
- [ ]`EvalSuite.run()` populates `EvalResult.usage` from `agent_usage + scorer_usage`
- [ ]`EvalSuite.run()` populates `EvalResult.cost` when `cost_calculator` is provided
- [ ]`EvalSuite.cost_efficiency` is `average_score / total_cost * 100`
- [ ]`EvalSuite.run()` with `ExactMatchScorer` returns `usage=None` (no scorer tokens)

### Phase 1 pitfalls

These mistakes appear repeatedly when starting Phase 1. Avoid them:

1. **`account_tokens()` inside the hot loop** — it's a network call to the provider and adds ~100ms latency per iteration. Use it once at startup for the overhead baseline. Use `token_counter()` (local, microseconds) inside the loop. The token account should be a configuration parameter for `LLMCostRouter` to avoid coupling the router to a specific provider's pricing API. In tests, use a stubbed `CostCalculator` that returns fixed costs.

2. **`LLMCostRouter` tests without mocking `litellm.model_cost`** — the pricing table updates when LiteLLM releases a new version. Tests that read live pricing are flaky by design. Pin `litellm.model_cost` to a fixed dict in test fixtures.

3. **Merging `Budget` and `IterationBudget`** — they look similar but are fundamentally different: `Budget` is an immutable value type (`frozen=True`) that returns a new instance on `consume()`; `IterationBudget` is a mutable shared counter with `asyncio.Lock` and `refund()`. Merging them produces a class that is simultaneously immutable and a shared mutable counter — a type contradiction.

4. **Forgetting to delete old tests after Refactor** — two test suites for the same module create ambiguity, not safety. When one passes and the other fails, you don't know which is correct. Delete immediately after Refactor step; don't let them accumulate.

### After Phase 2 is complete

All old swarm-runtime tests under `tests/unit/` and `tests/features/` are deleted once their intent is migrated. `tests/template/`, bench-specific tests, and tasks tests remain outside the core swarm migration.

Run the final check:
```bash
uv run tasks check   # lint + typecheck + test
uv run tasks vulture # no dead code
uv run tasks security # bandit clean
```

## Appendix

### Open questions or deferred items

- **Integration test strategy.** This spec covers unit tests + per-module TDD. Multi-agent flows (Swarm + bus + guardrails together) and end-to-end runs (`AgentRuntime.start()` through to `RunReport`) have no specified test discipline today.
- **Performance test harness.** `MessageCompactor` efficiency on large histories and large-swarm message-bus throughput should have measurable targets and a regression suite. Currently absent.
- **Flakiness budget.** No explicit target for acceptable flake rate; no policy for quarantining vs deleting flaky tests. (Detailed conventions for *detecting* flakes belong in `03-test-map.md`; the *budget* and *policy* live here.)
