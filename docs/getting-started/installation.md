# Installation

## Prerequisites

- **Python 3.13+** — pyarnes uses modern Python features (slots, frozen dataclasses, match statements)
- **[uv](https://github.com/astral-sh/uv)** — fast Python package manager with workspace support

## Install from source

```bash
git clone https://github.com/Cognitivemesh/pyarnes.git
cd pyarnes
uv sync
```

This installs all five workspace packages and their dev dependencies:

| Package | What it provides |
|---|---|
| `pyarnes-core` | Error types, lifecycle FSM, JSONL logging |
| `pyarnes-harness` | Agent loop, tool registry, output capture |
| `pyarnes-guardrails` | Path, command, and tool-allowlist safety checks |
| `pyarnes-bench` | Evaluation scoring framework |
| `pyarnes-api` | FastAPI REST endpoints |

## Verify installation

```bash
uv run tasks check    # runs lint + typecheck + all tests
```

You should see all tests pass:

```text
Results (0.6s):
    90 passed
```

## Start the API server

```bash
uv run uvicorn pyarnes_api.app:app --reload
```

Then open <http://localhost:8000/docs> for the interactive OpenAPI docs.

