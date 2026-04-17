# Testing

## Run tests

```bash
uv run tasks test          # run all tests
uv run tasks test:cov      # with coverage
uv run tasks watch         # TDD watch mode
```

## Test structure

```text
tests/
├── conftest.py            # shared fixtures
├── unit/                  # unit tests
│   ├── test_capture.py
│   ├── test_errors.py
│   ├── test_guardrails.py
│   ├── test_lifecycle.py
│   ├── test_logger.py
│   ├── test_loop.py
│   ├── test_registry.py
│   └── test_tool_log.py
└── features/              # BDD / Gherkin
    ├── harness.feature
    └── steps/
        └── test_harness_steps.py
```

## Testing libraries

- **pytest** — test framework
- **pytest-bdd** — Gherkin BDD scenarios
- **pytest-asyncio** — async test support
- **pytest-cov** — coverage reporting
- **pytest-sugar** — nicer test output
- **hypothesis** — property-based testing
- **pyinstrument** — profiling
