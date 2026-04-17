# Guardrails

**Module:** `pyarnes_guardrails.guardrails`

Guardrails validate tool calls before execution. They are composable — stack multiple guardrails via `GuardrailChain` and the first violation stops the chain.

## Guardrail ABC

All guardrails implement one method:

```python
def check(self, tool_name: str, arguments: dict[str, Any]) -> None:
    """Raise UserFixableError if the call violates this guardrail."""
```

If the call is safe, `check()` returns `None` silently. If it's dangerous, it raises `UserFixableError` with a human-readable message and prompt hint.

## Built-in guardrails

### PathGuardrail

Blocks tool calls that reference paths outside allowed root directories.

| Field | Default | Description |
|---|---|---|
| `allowed_roots` | `("/workspace",)` | Directory prefixes that tools may access |
| `path_keys` | `("path", "file", "directory", "target")` | Argument keys expected to contain file paths |

```python
g = PathGuardrail(allowed_roots=("/workspace", "/tmp"))
g.check("read_file", {"path": "/workspace/src/main.py"})  # OK
g.check("read_file", {"path": "/etc/passwd"})  # raises UserFixableError
```

### CommandGuardrail

Blocks shell commands matching dangerous regex patterns.

| Default blocked patterns |
|---|
| `rm -rf /` |
| `sudo` |
| `chmod 777` |
| `curl ... \| sh` |

### ToolAllowlistGuardrail

Only permits pre-approved tool names. If `allowed_tools` is empty, all tools are allowed.

```python
g = ToolAllowlistGuardrail(allowed_tools=frozenset({"echo", "read_file"}))
g.check("echo", {})         # OK
g.check("delete_all", {})   # raises UserFixableError
```

## GuardrailChain

Composes multiple guardrails. Runs them in order; the first violation stops the chain.

```python
chain = GuardrailChain(guardrails=[
    PathGuardrail(allowed_roots=("/workspace",)),
    CommandGuardrail(),
    ToolAllowlistGuardrail(allowed_tools=frozenset({"shell", "read_file"})),
])
chain.check("shell", {"command": "ls -la", "path": "/workspace/src"})
```

## Via the API

```bash
curl -X POST http://localhost:8000/api/v1/guardrails/check \
  -H "Content-Type: application/json" \
  -d '{"tool_name": "shell", "arguments": {"command": "sudo rm -rf /"}}'
# {"allowed": false, "violation": "Command blocked by pattern: \\bsudo\\b"}
```

