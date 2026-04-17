# pyarnes-core

The foundation package that all other pyarnes packages depend on.

## What it provides

| Module | Key classes | Purpose |
|---|---|---|
| `pyarnes_core.types` | `ToolHandler`, `ModelClient` | Abstract base classes for tools and LLM clients |
| `pyarnes_core.errors` | `HarnessError`, `TransientError`, `LLMRecoverableError`, `UserFixableError`, `UnexpectedError` | Four-error taxonomy for structured failure routing |
| `pyarnes_core.lifecycle` | `Phase`, `Lifecycle` | Finite-state machine for session tracking |
| `pyarnes_core.observe.logger` | `LogFormat`, `configure_logging()`, `get_logger()` | Structured JSONL logging via loguru |

## Dependencies

- `loguru` — the only runtime dependency

## Usage

```python
from pyarnes_core.errors import TransientError
from pyarnes_core.lifecycle import Lifecycle
from pyarnes_core.observe.logger import configure_logging, get_logger
from pyarnes_core.types import ToolHandler, ModelClient

# Configure logging at startup
configure_logging(level="INFO", json=True)

# Get a logger
logger = get_logger(__name__)
logger.info("starting up")
```

