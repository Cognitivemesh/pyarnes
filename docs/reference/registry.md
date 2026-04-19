---
persona: both
level: L2
tags: [reference, registry]
---

# Tool Registry

**Module:** `pyarnes_harness.tools.registry`

The `ToolRegistry` stores `ToolHandler` instances keyed by name. It validates that handlers are proper `ToolHandler` subclasses on registration.

## Usage

```python
from pyarnes_harness.tools.registry import ToolRegistry

registry = ToolRegistry()
registry.register("read_file", ReadFileTool())
registry.register("shell", ShellTool())

# Look up a handler
handler = registry.get("read_file")  # returns ReadFileTool or None

# List registered tools
print(registry.names)  # ["read_file", "shell"]

# Pass to AgentLoop
loop = AgentLoop(tools=registry.as_dict(), model=model)
```

## Methods

| Method | Description |
|---|---|
| `register(name, handler)` | Add a tool. Raises `ValueError` if duplicate, `TypeError` if not a `ToolHandler` |
| `get(name)` | Look up by name. Returns `None` if missing |
| `unregister(name)` | Remove a tool. Raises `KeyError` if not registered |
| `names` | Sorted list of registered tool names |
| `as_dict()` | Shallow copy of the internal `{name: handler}` mapping |
| `len(registry)` | Number of registered tools |
| `"name" in registry` | Check if a tool is registered |
