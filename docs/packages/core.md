# pyarnes-core

Core abstractions that all other pyarnes packages depend on.

## Modules

| Module | Contents |
|---|---|
| `pyarnes_core.types` | `ToolHandler`, `ModelClient` ABCs |
| `pyarnes_core.errors` | `HarnessError`, `TransientError`, `LLMRecoverableError`, `UserFixableError`, `UnexpectedError`, `Severity` |
| `pyarnes_core.lifecycle` | `Phase`, `Lifecycle` FSM |
| `pyarnes_core.observe.logger` | `LogFormat`, `configure_logging()`, `get_logger()` |

## Dependencies

- `loguru` — structured logging backend
