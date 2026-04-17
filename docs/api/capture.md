# Capture

**Modules:** `pyarnes_harness.capture.output`, `pyarnes_harness.capture.tool_log`

The capture system records everything that happens during tool execution — stdout, stderr, return values, errors, durations, and timestamps.

## OutputCapture

High-level capture that records tool execution results as `CapturedOutput` records.

```python
from pyarnes_harness.capture.output import OutputCapture

capture = OutputCapture()

# Record a success
record = capture.record_success("echo", {"text": "hi"}, result="hi", duration=0.01)
print(record.succeeded)  # True

# Record a failure
record = capture.record_failure("broken", {}, RuntimeError("boom"), duration=0.1)
print(record.succeeded)  # False
print(record.error)      # "boom"

# Get all records
for entry in capture.history:
    print(entry.as_dict())

capture.clear()  # discard all records
```

### CapturedOutput fields

| Field | Type | Description |
|---|---|---|
| `tool_name` | `str` | Name of the tool |
| `arguments` | `dict` | Arguments passed to the tool |
| `stdout` | `str` | Captured standard output |
| `stderr` | `str` | Captured standard error |
| `return_value` | `Any` | Tool's return value (if successful) |
| `error` | `str \| None` | Error message (if failed) |
| `traceback_str` | `str \| None` | Full traceback (if failed) |
| `duration_seconds` | `float` | Wall-clock execution time |
| `timestamp` | `float` | Unix timestamp when capture started |

## ToolCallLogger

Append-only JSONL logger that persists every tool call to a file on disk.

```python
from pathlib import Path
from pyarnes_harness.capture.tool_log import ToolCallLogger

with ToolCallLogger(path=Path(".harness/tool_calls.jsonl")) as log:
    entry = log.log_call("read_file", {"path": "a.py"}, result="contents...")
```

Each entry is written as a single JSON line:

```json
{
  "tool": "read_file",
  "arguments": {"path": "a.py"},
  "result": "contents...",
  "is_error": false,
  "started_at": "2026-04-17T15:00:00+00:00",
  "finished_at": "2026-04-17T15:00:01+00:00",
  "duration_seconds": 0.42
}
```

### File location

The JSONL file is created at whatever path you pass to `ToolCallLogger(path=...)`. Parent directories are created automatically. The file is opened in **append mode** and flushed after every write, so partial runs are never lost.

### Integration with AgentLoop

Pass a `ToolCallLogger` to `AgentLoop` and every tool call (success and failure) is automatically logged:

```python
loop = AgentLoop(
    tools=registry.as_dict(),
    model=model,
    tool_call_logger=ToolCallLogger(path=Path(".harness/calls.jsonl")),
)
```

