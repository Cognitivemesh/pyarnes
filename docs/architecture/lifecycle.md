# Lifecycle

The `Lifecycle` class is a finite-state machine tracking session phases:

```text
INIT → RUNNING → PAUSED → RUNNING → COMPLETED
                                  → FAILED
```

## Valid transitions

| From | To |
|---|---|
| INIT | RUNNING, FAILED |
| RUNNING | PAUSED, COMPLETED, FAILED |
| PAUSED | RUNNING, FAILED |
| COMPLETED | *(terminal)* |
| FAILED | *(terminal)* |

## Usage

```python
from pyarnes.harness.lifecycle import Lifecycle

lc = Lifecycle(metadata={"session_id": "abc123"})
lc.start()     # INIT → RUNNING
lc.pause()     # RUNNING → PAUSED
lc.resume()    # PAUSED → RUNNING
lc.complete()  # RUNNING → COMPLETED

print(lc.history)  # list of transition events with timestamps
```
