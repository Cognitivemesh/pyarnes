# 04 — Adopter C (RTM + Toggl → agile) and meta-use dev hooks

## Context

Adopter C is the plan's key twist: pyarnes appears *twice* in the project. Once as the shipped runtime (same pattern as A and B) and **again as the dev-time harness that tracks, gates, and scores the coding agent itself**. This spec ships both halves:

1. `packages/examples/rtm-toggl-agile/` — the shipped pipeline: RTM + Toggl → normalise → unified agile workspace.
2. Dev-time hooks in `template/.claude/hooks/` that adopters opt into. The hooks import `pyarnes_core`, `pyarnes_guardrails`, and `pyarnes_harness.capture` to harness the coding agent during development.

The plan's "Meta-use" table maps every pyarnes package to a dev-time use. This spec turns that table into code and template-stamped files.

## Goals / Non-goals

**Goals**

- `packages/examples/rtm-toggl-agile/` — full reference implementation with the same fidelity as A and B (CLI, tools, guardrails, tests, feature test).
- Template-stamped Claude Code pre-tool-use and post-tool-use hooks that wire `GuardrailChain` + `ToolCallLogger` + `get_logger` into the coding agent's activity.
- A `tests/bench/test_agent_quality.py` scaffold that drives `EvalSuite` across labeled coding scenarios and asserts a minimum pass rate.
- Clear `.pyarnes/` directory layout: `.pyarnes/dev.jsonl` (session logs), `.pyarnes/agent_tool_calls.jsonl` (audit trail).
- Opt-in via Copier toggle `enable_dev_hooks` (default **on** when `adopter_shape=rtm-toggl-agile`, default **off** otherwise).

**Non-goals**

- Claude-Code-specific hook-protocol changes. We target the documented `PreToolUse` / `PostToolUse` hook interface as it exists today.
- Invention of new scorers beyond what the plan names (`DiffSimilarityScorer`, `TestsPassScorer`, `TaskCompletionScorer`). These are minimal; adopters extend.
- Shipping a labeled coding-scenarios corpus. Template ships 2 trivial fixtures; adopters grow their own corpus.

## Proposed design

### Part 1 — `packages/examples/rtm-toggl-agile/`

**Shape:** connect to `rememberthemilk.com` + `toggl.com`, download tasks/time entries, normalise into a shared schema, push into a unified agile backend (stories, sprints, WIP limits, time tracking tied to stories).

Key files:

- `src/rtm_toggl_agile/cli.py` — Typer: `sync-rtm`, `sync-toggl`, `promote`.
- `src/rtm_toggl_agile/pipeline.py` — builds loop; wires `ApiQuotaGuardrail` and `SecretScanGuardrail`.
- `src/rtm_toggl_agile/tools/rtm.py` — `ListRtmTasksHandler`, `FetchRtmTaskHandler`.
- `src/rtm_toggl_agile/tools/toggl.py` — `ListTogglEntriesHandler`, `FetchTogglProjectHandler`.
- `src/rtm_toggl_agile/tools/agile.py` — `CreateStoryHandler`, `LinkTimeEntryHandler`, `PromoteToSprintHandler`.
- `src/rtm_toggl_agile/schema.py` — Pydantic models for the shared schema (story, time entry, tag, sprint).
- `src/rtm_toggl_agile/guardrails.py`:
  - `ApiQuotaGuardrail` — rate-limits RTM/Toggl calls per minute.
  - `SecretScanGuardrail` — rejects any tool arg or result containing a credential pattern before it's logged.
- `tests/unit/test_mapping.py` — lossless round-trip through the shared schema.
- `tests/features/unified_sync.feature` — full RTM+Toggl → agile-backend path with `respx`/`pytest-httpx` mocked servers.

Runtime deps: `httpx`, `pydantic`, `typer`.

### Part 2 — Dev-time hooks (template)

**Files stamped when `enable_dev_hooks=true`:**

- `template/.claude/hooks/pyarnes_pre_tool.py.jinja`
- `template/.claude/hooks/pyarnes_post_tool.py.jinja`
- `template/.claude/settings.json.jinja` — registers both hooks under `PreToolUse` / `PostToolUse`.
- `template/.pyarnes/.gitignore.jinja` — ignores `*.jsonl` inside `.pyarnes/` so audit logs don't land in git.

**Pre-tool-use hook (full, not pseudocode):**

```python
import json, sys
from pyarnes_core.errors import UserFixableError
from pyarnes_core.observe.logger import get_logger, configure_logging, LogFormat
from pyarnes_guardrails import (
    GuardrailChain, PathGuardrail, CommandGuardrail, ToolAllowlistGuardrail,
)

configure_logging(format=LogFormat.JSON, level="INFO")
log = get_logger("coding_agent.pre_tool")

CHAIN = GuardrailChain(guardrails=[
    PathGuardrail(allowed_roots=("{{ repo_root }}",), path_keys=("path", "file_path")),
    CommandGuardrail(),
    ToolAllowlistGuardrail(allowed_tools=frozenset({
        "Read", "Write", "Edit", "Glob", "Grep", "Bash", "TodoWrite",
    })),
])

event = json.load(sys.stdin)
tool, args = event["tool_name"], event["tool_input"]
log.info("tool.pre tool={tool}", tool=tool)
try:
    CHAIN.check(tool, args)
except UserFixableError as exc:
    print(json.dumps({"decision": "block", "reason": str(exc)}))
    sys.exit(2)
```

**Post-tool-use hook:**

```python
import json, sys
from pyarnes_harness.capture import ToolCallLogger

logger = ToolCallLogger(path=".pyarnes/agent_tool_calls.jsonl")
event = json.load(sys.stdin)
logger.log_call(
    event["tool_name"], event["tool_input"],
    result=str(event.get("tool_response", "")),
    is_error=bool(event.get("is_error", False)),
    started_at=event["started_at"],
    finished_at=event["finished_at"],
    duration_seconds=event["finished_at"] - event["started_at"],
)
```

### Part 3 — Agent-quality bench

`template/tests/bench/test_agent_quality.py.jinja` (stamped only with `enable_dev_hooks=true`):

- Defines `DiffSimilarityScorer` and `TestsPassScorer` locally (minimal, ~20 lines each). Upstreaming to `pyarnes-bench` is deferred.
- Loads labeled scenarios from `tests/bench/scenarios/<shape>/*.yaml`.
- Runs the coding agent over each scenario's workspace and collects `EvalResult`s into an `EvalSuite`.
- Asserts `suite.summary()["pass_rate"] >= 0.80`.

Ships two tiny fixture scenarios under `template/tests/bench/scenarios/rtm/` so the test is runnable immediately and the corpus structure is copy-able.

### `.pyarnes/` directory contract

- `.pyarnes/dev.jsonl` — structured logs from `get_logger("coding_agent.*")` (stderr → file via `configure_logging` with a file sink configured in the hook scripts).
- `.pyarnes/agent_tool_calls.jsonl` — `ToolCallLogger` output.
- `.pyarnes/.gitignore` — `*.jsonl`.

### Copier changes (on top of Spec 02)

```yaml
enable_dev_hooks:
  type: bool
  help: Wire pyarnes into Claude Code hooks to harness the coding agent during development?
  default: "{{ adopter_shape == 'rtm-toggl-agile' }}"
```

`_tasks` post-generation hook ensures `.pyarnes/` exists and `.gitignore` is in place.

## Tests / acceptance

- `uv run --package rtm-toggl-agile pytest` green.
- `tests/unit/test_dev_hooks.py` — injects a synthetic `PreToolUse` event (`tool=Bash`, `command=rm -rf /`), runs `pyarnes_pre_tool.py` as a subprocess, asserts exit code 2 and a JSON `{"decision": "block", ...}` payload. Reads `.pyarnes/dev.jsonl` and asserts a `guardrail.command_blocked` log line.
- `tests/unit/test_post_tool.py` — injects a synthetic `PostToolUse` event, asserts a JSONL line appended to `.pyarnes/agent_tool_calls.jsonl` with the expected fields.
- `uv run tasks bench:agent` — runs the two shipped fixture scenarios; passes with `pass_rate = 1.0`. (Real corpora live per-adopter.)
- Scaffold test: `uvx copier copy . /tmp/t-c --data adopter_shape=rtm-toggl-agile --defaults` produces `.claude/hooks/pyarnes_pre_tool.py` and `.claude/settings.json` referencing both hooks.
- Scaffold test: `uvx copier copy . /tmp/t-a --data adopter_shape=pii-redaction --defaults` does **not** produce `.claude/hooks/` unless `enable_dev_hooks=true` is explicitly set.

## Open questions

- Do the custom scorers (`DiffSimilarityScorer`, `TestsPassScorer`) belong in `pyarnes-bench` (stable surface, Spec 01 would need updating) or stay as adopter code? Leaning adopter-code until a second adopter needs them.
- Should the hook scripts self-update via `uv run tasks update` when the template evolves? Probably yes — covered by `_migrations`; defer concrete design.
- `ToolAllowlistGuardrail` lists tool names as strings. Do we want a shared constants module so typos are caught? Defer.
- What happens on Windows/PowerShell for the hook's `sys.exit(2)` block semantic? Claude Code hook docs confirm exit code 2 blocks on all platforms; re-verify when this ships.

Next: `05-docs-distribution-and-meta-use.md`
