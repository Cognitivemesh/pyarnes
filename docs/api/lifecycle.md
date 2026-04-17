# Lifecycle

**Module:** `pyarnes_core.lifecycle`

See the full documentation at [Architecture → Lifecycle](../architecture/lifecycle.md).

## Quick reference

```python
from pyarnes_core.lifecycle import Lifecycle, Phase

lc = Lifecycle(metadata={"session_id": "abc123"})
lc.start()     # INIT → RUNNING
lc.pause()     # RUNNING → PAUSED
lc.resume()    # PAUSED → RUNNING
lc.complete()  # RUNNING → COMPLETED

lc.phase        # Phase.COMPLETED
lc.is_terminal  # True
lc.history      # [{"from": "init", "to": "running", "timestamp": ...}, ...]
```

## Phase enum

`INIT`, `RUNNING`, `PAUSED`, `COMPLETED`, `FAILED`

## Lifecycle methods

| Method | Effect |
|---|---|
| `start()` | → RUNNING |
| `pause()` | → PAUSED |
| `resume()` | → RUNNING (from PAUSED) |
| `complete()` | → COMPLETED |
| `fail()` | → FAILED |
| `transition(target)` | Direct transition (validates) |

