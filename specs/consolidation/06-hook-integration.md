# pyarnes_swarm — Claude Code Hook Integration

## Design Rationale

**Why the "meta-use" pattern?** Most libraries are used in one direction: your code imports the library. Here, `pyarnes_swarm` is imported *twice* — by the agent under construction AND by the Claude Code hooks that govern that agent. This is unusual but intentional: the same safety primitives (guardrails, budgets) that protect the agent's own tool calls should also protect the coding agent building those tools. One library, one set of primitives, two integration points.

**Why `consume()` returns `False` instead of raising `BudgetExhaustedError`?** An exception unwinds the stack. If the agent is mid-tool-execution when the budget is exhausted, an exception would lose the in-progress result. A `False` return lets the agent finish its current action cleanly, store the result, and then stop at the top of the loop. Cooperative termination preserves work; exception-based termination loses it.

**Why does the `Stop` hook use `Budget.allows()` instead of `IterationBudget`?** The `Stop` hook runs at session end — it's checking cumulative spend over the whole session, not the remaining iteration count. `Budget` is the right tool: it's an immutable record of what was spent, checked against a cap. `IterationBudget` tracks remaining steps for an active loop — it has no meaning at session end.

## Overview

Claude Code fires hooks at specific lifecycle events. `pyarnes_swarm` provides two primitives that map directly onto the two most useful hook points:

| Hook type | Claude Code event | pyarnes_swarm primitive |
|---|---|---|
| `PreToolUse` | Before any tool call | `GuardrailChain.check()` |
| `PostToolUse` | After any tool call | `ToolCallLogger.log_call()` + `IterationBudget.consume()` |
| `Stop` | Agent session ends | `Budget.consume()` — record calls/seconds/tokens |

This is the "meta-use" pattern: `pyarnes_swarm` is imported **twice** — once by the agent's own tools, and once by the Claude Code hooks that govern the coding agent writing those tools.

## `PreToolUse` hook — guardrail enforcement

`.claude/hooks/pre_tool_use.py`:

```python
import json
import sys

from pyarnes_swarm.guardrails import GuardrailChain
from pyarnes_swarm.guardrails import PathGuardrail, CommandGuardrail, ToolAllowlistGuardrail
from pyarnes_swarm.observability import configure_logging, get_logger
from pyarnes_swarm.errors import UserFixableError

configure_logging(fmt="json", level="INFO")
log = get_logger("claude_code.pre_tool")

CHAIN = GuardrailChain([
    PathGuardrail(allowed_roots=("./workspace",)),
    CommandGuardrail(),
    ToolAllowlistGuardrail(allowed_tools=frozenset({
        "Read", "Write", "Edit", "Glob", "Grep", "Bash",
    })),
])

event = json.load(sys.stdin)
try:
    CHAIN.check(event["tool_name"], event.get("tool_input", {}))
except UserFixableError as exc:
    print(json.dumps({"decision": "block", "reason": str(exc)}))
    sys.exit(2)
```

Exit code 2 = block the tool call. Claude Code surfaces the block reason to the model.

## `PostToolUse` hook — audit trail + iteration budget

`.claude/hooks/post_tool_use.py`:

```python
import json
import sys
from pathlib import Path

from pyarnes_swarm.capture import ToolCallLogger

logger = ToolCallLogger(path=Path(".pyarnes/agent_tool_calls.jsonl"))
event = json.load(sys.stdin)

logger.log_call(
    event["tool_name"],
    event.get("tool_input", {}),
    result=str(event.get("tool_response", "")),
    is_error=bool(event.get("is_error", False)),
    started_at=event.get("started_at"),
    finished_at=event.get("finished_at"),
    duration_seconds=event.get("duration_seconds"),
)
```

## `Stop` hook — session budget enforcement

`.claude/hooks/stop.py`:

```python
import json
import sys
from pathlib import Path

from pyarnes_swarm.budget import Budget

# Load the session cap from a config file or env var
cap = Budget(
    max_tool_calls=200,
    max_seconds=3600.0,
    max_tokens=500_000,
)

# Load accumulated usage from a persistent JSON file (written by PostToolUse hook)
usage_path = Path(".pyarnes/session_usage.json")
if usage_path.exists():
    usage = json.loads(usage_path.read_text())
    current = Budget(**usage)
    if not cap.allows(current):
        print(json.dumps({"decision": "block",
                          "reason": f"Session budget exceeded: {current}"}))
        sys.exit(2)
```

`Budget.allows()` checks whether `current` usage is still within the cap's limits. This integrates with Claude Code's `Stop` hook to hard-stop sessions that exceed per-session spend.

## `.pyarnes/` directory layout

```
.pyarnes/
├── dev.jsonl                  # structured log events from hooks
├── agent_tool_calls.jsonl     # ToolCallLogger audit trail (PostToolUse)
├── session_usage.json         # accumulated calls/seconds/tokens (Stop hook)
└── .gitignore                 # "*.jsonl" — audit logs don't land in git
```

JSONL schema matches the runtime schema — one `jq` invocation inspects both.

## `IterationBudget` in swarm mode

When running a multi-agent swarm, share one `IterationBudget` across parent + all sub-agents:

```python
from pyarnes_swarm.budget import IterationBudget
from pyarnes_swarm import Swarm, AgentSpec

budget = IterationBudget(max_iterations=500)

shared_config = LoopConfig(budget=budget)   # budget lives in LoopConfig, not AgentSpec

swarm = Swarm(
    bus=TursoMessageBus(),
    agents=[
        AgentSpec(name="orchestrator", config=shared_config, ...),
        AgentSpec(name="worker-1",     config=shared_config, ...),
        AgentSpec(name="worker-2",     config=shared_config, ...),
    ],
)
```

`IterationBudget.consume()` is async and thread-safe via `asyncio.Lock`. When the budget is exhausted, `consume()` returns `False` and the loop terminates cleanly. Sub-agents can call `refund()` if they finish early, returning unused steps to the shared pool.

### Budget exhaustion and refund patterns

```python
import asyncio
from pyarnes_swarm.budget import IterationBudget

budget = IterationBudget(max_iterations=500)

# Agent loop checks the budget before each step
async def agent_loop(budget: IterationBudget) -> None:
    while True:
        allowed = await budget.consume()      # acquires lock, decrements
        if not allowed:
            # Budget exhausted — terminate cleanly rather than raising
            break
        action = await model.next_action(messages)
        if action["type"] == "final_answer":
            break
        result = await tools.execute(action)
        messages.append(result)

# Sub-agent that may finish early returns unused steps
async def sub_agent(budget: IterationBudget, steps_reserved: int) -> str:
    steps_used = 0
    while steps_used < steps_reserved:
        allowed = await budget.consume()
        if not allowed:
            break
        # ... do work ...
        steps_used += 1
        if task_complete():
            # Return unused steps to the shared pool
            unused = steps_reserved - steps_used
            if unused > 0:
                await budget.refund(unused)
            break
    return result
```

`consume()` returns `False` without raising — the caller decides whether that is an error or a clean stop. `refund()` adds steps back to the pool so sibling agents can use them; call it only when you know you will do no more work.

## Enabling hooks in a Copier scaffold

At scaffold time, `enable_dev_hooks: true` installs the three hook files under `.claude/hooks/`. The hook files are stamped from the template and reference `pyarnes_swarm` at the git-pinned `pyarnes_ref`.

```yaml
# copier.yml
enable_dev_hooks:
  type: bool
  default: false
  help: "Install Claude Code hooks that log tool calls and enforce guardrails"
```

When `true`, the scaffold adds:
- `.claude/hooks/pre_tool_use.py` — guardrail enforcement
- `.claude/hooks/post_tool_use.py` — audit trail
- `.claude/hooks/stop.py` — session budget
- `.claude/settings.json` — hooks registration
- `.pyarnes/.gitignore` — excludes JSONL logs from git

## Relationship to `claudecode-pyarnes-judge-plugin.md`

The judge plugin spec describes a separate Claude Code plugin that auto-scores sub-agent reports via `SubagentStop` hook + `RaceEvaluator`/`FactEvaluator`. That plugin uses `pyarnes_swarm` as a library dependency (imports `RaceEvaluator`, `FactEvaluator`). The plugin itself is not part of `pyarnes_swarm` — it's a separate `plugin/pyarnes-judge/` directory. When implemented, it requires zero library changes.
