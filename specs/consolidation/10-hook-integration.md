# pyarnes_swarm — External Hook Integration (Claude Code)

> **Spec header**
>
> | Field | Value |
> |---|---|
> | **Title** | pyarnes_swarm — External Hook Integration (Claude Code) |
> | **Status** | active |
> | **Type** | integrations-safety |
> | **Tags** | claude-code, hooks, integration, safety |
> | **Owns** | external Claude Code lifecycle hooks (PreToolUse, PostToolUse, Stop), stdin JSON contract, exit code semantics, settings.json registration, .pyarnes/ directory layout, adopter shapes (pii-redaction, s3-sweep, rtm-toggl-agile) |
> | **Depends on** | 07-swarm-api.md |
> | **Extends** | 09-loop-hooks.md |
> | **Supersedes** | 23-claude-judge-plugin.md (deferred subsection) |
> | **Read after** | 09-loop-hooks.md |
> | **Read before** | 11-message-safety.md |
> | **Not owned here** | internal in-process hooks / PreToolHook / PostToolHook (see `09-loop-hooks.md`); model selection (see `06-model-router.md`); evaluation semantics (see `15-bench-integrated-axes.md`); message-safety pipeline (see `11-message-safety.md`); judge-plugin design notes (see `23-claude-judge-plugin.md`, deferred appendix) |
> | **Last reviewed** | 2026-04-29 |

## Design Rationale

**Why the "meta-use" pattern?** Most libraries are used in one direction: your code imports the library. Here, `pyarnes_swarm` is imported *twice* — by the agent under construction AND by the Claude Code hooks that govern that agent. This is unusual but intentional: the same safety primitives (guardrails, budgets) that protect the agent's own tool calls should also protect the coding agent building those tools. One library, one set of primitives, two integration points.

**Why `consume()` returns `False` instead of raising `BudgetExhaustedError`?** !!! note "Budget exhaustion is cooperative, not exceptional"
    An exception unwinds the stack. If the agent is mid-tool-execution when the budget is exhausted, an exception would lose the in-progress result. A `False` return lets the agent finish its current action cleanly, store the result, and then stop at the top of the loop. Cooperative termination preserves work; exception-based termination loses it.

**Why does the `Stop` hook use `Budget.allows()` instead of `IterationBudget`?** The `Stop` hook runs at session end — it's checking cumulative spend over the whole session, not the remaining iteration count. `Budget` is the right tool: it's an immutable record of what was spent, checked against a cap. `IterationBudget` tracks remaining steps for an active loop — it has no meaning at session end.

## Specification

### Overview

Compose from bottom up:

- [ ] **Atoms**: single-purpose guardrails, budget helpers, loggers
- [ ] **Molecules**: ordered `GuardrailChain`, checkpoint file helpers
- [ ] **Organisms**: register in `.claude/settings.json`; entrypoints called by Claude Code

Claude Code fires hooks at specific lifecycle events. The shipped template is intentionally layered rather than monolithic:

| Layer | What lives here | Current examples |
|---|---|---|
| Atoms | Single-purpose leaf primitives | `PathGuardrail`, `CommandGuardrail`, `SecretLeakGuardrail`, `ToolCallLogger`, `Budget`, `Lifecycle.load()`, `Lifecycle.dump()` |
| Molecules | Ordered composites that assemble atoms without talking to Claude Code directly | `GuardrailChain`, the budget/checkpoint file helpers inside the hook scripts |
| Organisms | Claude Code-facing entrypoints | `pyarnes_pre_tool.py`, `pyarnes_post_tool.py`, `pyarnes_stop.py`, `pyarnes_session_start.py`, `pyarnes_session_end.py`, all registered in `.claude/settings.json` |

That layering is descriptive, not a naming convention. The same atoms are reused in-process inside `AgentLoop` (`09-loop-hooks.md`) and out-of-process inside the Claude Code hook scripts owned here.

| Hook type | Claude Code event | Composed behaviour |
|---|---|---|
| `PreToolUse` | Before any tool call | leaf guardrails → `GuardrailChain.check()` |
| `PostToolUse` | After any tool call | `ToolCallLogger.log_call()` + `SecretLeakGuardrail.check()` + flat `Budget.consume(calls=1)` persistence |
| `Stop` | Claude Code asks whether the session should stop | `Budget.exceeded_cap()` over the persisted flat counter |
| `SessionStart` | Session boot | `Lifecycle.load()` + `additionalContext` restore |
| `SessionEnd` | Session teardown | `Lifecycle.load()` / `Lifecycle.dump()` + merge the flat budget counter into the checkpoint |

<div class="artifact" data-artifact="hook-wiring"></div>

This is the "meta-use" pattern: `pyarnes_swarm` is imported **twice** — once by the agent's own tools, and once by the Claude Code hooks that govern the coding agent writing those tools.

In the current repo, those same atoms are still split across `pyarnes_core`, `pyarnes_guardrails`, and `pyarnes_harness`; the linkage above is the assembly path those packages already form today.

### `PreToolUse` hook — guardrail enforcement

`.claude/hooks/pre_tool_use.py`:

```python
import asyncio
import json
import sys

from pyarnes_swarm.guardrails import GuardrailChain
from pyarnes_swarm.guardrails import (
  CommandGuardrail,
  NetworkEgressGuardrail,
  PathGuardrail,
  RateLimitGuardrail,
  SecretLeakGuardrail,
  ToolAllowlistGuardrail,
)
from pyarnes_swarm.observability import configure_logging, get_logger
from pyarnes_swarm.errors import UserFixableError

configure_logging(fmt="json", level="INFO")
log = get_logger("claude_code.pre_tool")

# organism: Claude Code executes this entrypoint
# molecule: one ordered GuardrailChain
CHAIN = GuardrailChain([
  # atoms: reusable leaf checks
  PathGuardrail(allowed_roots=("./workspace",)),
  CommandGuardrail(),
  SecretLeakGuardrail(),
  NetworkEgressGuardrail(allowed_hosts=("github.com", "pypi.org")),
  RateLimitGuardrail(max_calls=120, window_seconds=60.0),
  ToolAllowlistGuardrail(allowed_tools=frozenset({
    "Read", "Write", "Edit", "Glob", "Grep", "Bash",
  })),
])

event = json.load(sys.stdin)
try:
  asyncio.run(CHAIN.check(event["tool_name"], event.get("tool_input", {})))
except UserFixableError as exc:
    print(json.dumps({"decision": "block", "reason": str(exc)}))
    sys.exit(2)
```

Exit code 2 = block the tool call. Claude Code surfaces the block reason to the model. The shipped template also records a `Violation` row for blocked calls; the important linkage is that the hook script stays thin because the leaf guardrails and the chain do the real work.

### `PostToolUse` hook — audit trail + secret scan + flat budget tick

`.claude/hooks/post_tool_use.py`:

```python
import json
import sys
from pathlib import Path

from pyarnes_swarm.capture import ToolCallLogger
from pyarnes_swarm.guardrails import SecretLeakGuardrail
from pyarnes_swarm import Budget

# organism: Claude Code executes this entrypoint
# atoms: logger, output scanner, and Budget value object
logger = ToolCallLogger(path=Path(".pyarnes/agent_tool_calls.jsonl"))
scanner = SecretLeakGuardrail()
event = json.load(sys.stdin)

# molecule: append audit row first
logger.log_call(
    event["tool_name"],
    event.get("tool_input", {}),
    result=str(event.get("tool_response", "")),
    is_error=bool(event.get("is_error", False)),
    started_at=event.get("started_at"),
    finished_at=event.get("finished_at"),
    duration_seconds=event.get("duration_seconds"),
)

# molecule: then scan the emitted output and tick the flat session counter
scanner.check(event["tool_name"], {"output": str(event.get("tool_response", ""))})
budget = Budget.from_dict(load_budget_json()).consume(calls=1)
write_budget_json(budget.as_dict())
```

### `Stop` hook — session budget enforcement

`.claude/hooks/stop.py`:

```python
import json
import sys
from pathlib import Path

from pyarnes_swarm.budget import Budget

# organism: narrow Claude Code decision hook
event = json.load(sys.stdin)
path = Path(f".claude/pyarnes/budget-{event['session_id']}.json")
if path.exists():
  budget = Budget.from_dict(json.loads(path.read_text()))
  cap = budget.exceeded_cap()
  if cap is not None:
    print(json.dumps({
      "continue": False,
      "stopReason": f"pyarnes.Budget cap {cap!r} exceeded: {budget.as_dict()}",
    }))
```

`Stop` stays deliberately narrow: it does not mutate lifecycle state or recompute usage. It only reads the flat counter file that `PostToolUse` has been maintaining and answers Claude Code's continue/stop question.

### Session hooks — lifecycle checkpointing

`SessionStart` and `SessionEnd` are where the lifecycle FSM enters the picture. They are separate organisms because they speak a different Claude Code contract from `PreToolUse` / `PostToolUse` / `Stop`.

```python
# SessionStart organism: restore checkpoint -> surface context
lifecycle = Lifecycle.load(checkpoint_path)
print({"hookSpecificOutput": {"additionalContext": f"pyarnes checkpoint restored: {summary}"}})

# SessionEnd organism: fold flat budget into lifecycle -> persist checkpoint
lifecycle = Lifecycle.load(checkpoint_path) if checkpoint_exists else Lifecycle(...)
lifecycle.budget = load_budget_or_none(budget_path)
lifecycle.complete()
lifecycle.dump(checkpoint_path)
```

This split is the key linkage to `09-loop-hooks.md`: internal `HookChain` wraps tool execution inside `AgentLoop`, while external Claude Code session hooks wrap the editor session around it. Same atoms, different boundary.

### `.pyarnes/` and `.claude/pyarnes/` directory layout

```
.pyarnes/
├── agent_tool_calls.jsonl          # ToolCallLogger audit trail (PostToolUse)
└── .gitignore                      # "*.jsonl" — audit logs don't land in git

.claude/pyarnes/
├── budget-<session_id>.json        # flat Budget counter written by PostToolUse
├── checkpoint-<session_id>.json    # Lifecycle snapshot persisted by SessionEnd
└── violations.jsonl                # Pre/Post hook violation audit trail
```

The split is deliberate: `.pyarnes/` holds the append-only audit stream shared with the runtime, while `.claude/pyarnes/` holds hook-private state keyed by `session_id`.

### `IterationBudget` in swarm mode

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

#### Budget exhaustion and refund patterns

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

### Enabling hooks in a Copier scaffold

At scaffold time, `enable_dev_hooks: true` installs the five hook files under `.claude/hooks/`. In the current monorepo they import the same atoms from `pyarnes_core`, `pyarnes_guardrails`, and `pyarnes_harness`; after consolidation those imports collapse under `pyarnes_swarm` at the git-pinned `pyarnes_ref`.

```yaml
# copier.yml
enable_dev_hooks:
  type: bool
  default: false
  help: "Install Claude Code hooks that log tool calls and enforce guardrails"
```

When `true`, the scaffold adds:
- `.claude/hooks/pre_tool_use.py` — guardrail enforcement
- `.claude/hooks/post_tool_use.py` — audit trail + output secret scan + flat budget tick
- `.claude/hooks/stop.py` — session stop decision from the flat budget counter
- `.claude/hooks/session_start.py` — `Lifecycle.load()` restore + `additionalContext`
- `.claude/hooks/session_end.py` — `Lifecycle.dump()` checkpoint persistence
- `.claude/settings.json` — hooks registration
- `.pyarnes/.gitignore` — excludes JSONL logs from git

### Deferred: Claude Code judge plugin

A separate Claude Code plugin — `pyarnes-judge` — is planned to auto-score sub-agent reports inline. It is **deferred**: the library layer in `pyarnes_swarm.bench` is already sufficient, and plugin packaging is a distinct concern that can ship later without any library changes.

**Plugin scope.** The plugin lives outside the library, in its own directory `plugin/pyarnes-judge/` (manifest `.claude-plugin/plugin.json`, two skills `race-evaluate` and `fact-check`, one hook handler, and ~80 lines of glue Python). It is **not** part of `pyarnes_swarm` — it consumes `pyarnes_swarm` the same way an adopter project would.

**Hook used: `SubagentStop`.** Claude Code fires `SubagentStop` when a sub-agent dispatched via the `Task` tool finishes. The plugin registers a narrow matcher (`Explore|Research|general-purpose`) so noisy or unrelated sub-agents do not trigger evaluation.

**What it does.** On `SubagentStop`, the hook reads the sub-agent's `last_assistant_message` from stdin, then auto-scores it via:
- `RaceEvaluator` — for long-form research reports (4-dimension RACE framework, LLM-as-judge).
- `FactEvaluator` — for citation-heavy reports (Accuracy + Effective Citations; requires a pre-fetched URL→content map).

A reentrancy guard (`PYARNES_JUDGE_INFLIGHT=1`) prevents the judge's own `claude -p` calls from triggering nested `SubagentStop` events.

**Library dependencies.** The plugin imports the following from `pyarnes_swarm.bench`, with **zero** library-side changes required:

```python
from pyarnes_swarm.bench import RaceEvaluator, FactEvaluator
from pyarnes_swarm.bench import ScoreResult  # RaceScore / FactMetrics result types
```

No duplicated scoring, weighting, citation, or aggregation logic lives in the plugin — its Python is adapter (`ClaudeCliJudge`, a ~20-line `ModelClient` that shells out to `claude -p`) plus a ~60-line argparse CLI that wires the judge into the evaluators and emits JSON.

**Hook output schema (illustrative).** `SubagentStop` writes a JSON payload back to Claude Code with the evaluator result and a short human summary. Minimal sketch:

```json
{
  "decision": "block_or_continue",
  "reason": "RACE score 0.72 — comprehensiveness weak (0.55).",
  "additional_context": {
    "mode": "race",
    "result": {
      "final_score": 0.72,
      "dimensions": {
        "comprehensiveness": 0.55,
        "insight": 0.78,
        "instruction_following": 0.81,
        "readability": 0.74
      },
      "warnings": []
    }
  }
}
```

For `--mode fact`, `additional_context.result` carries `FactMetrics` fields (`citation_accuracy`, `effective_citations`, supported/total claim counts) instead.

**Why deferred.** The library surface in `pyarnes_swarm.bench` already meets every need this plugin will have. Plugin packaging (manifest, skills, hooks.json, shell wrapper, CLI subprocess adapter for `claude -p`) is independent of the library and can be shipped later with no upstream coupling.

---

### Adopter shapes (Copier template)

#### Scaffold command and `pyarnes_ref` pinning

New projects are bootstrapped with a single command:

```bash
uvx copier copy gh:Cognitivemesh/pyarnes <dest>
```

Copier asks two questions that govern everything stamped into the project:

```yaml
# copier.yml
adopter_shape:
  type: str
  help: Which reference shape best fits this project?
  choices:
    - pii-redaction
    - s3-sweep
    - rtm-toggl-agile
    - blank
  default: blank

pyarnes_ref:
  type: str
  help: Git ref of pyarnes_swarm to pin (tag, branch, or commit SHA).
  default: main
```

The generated `pyproject.toml` pins `pyarnes_swarm` as a single git dependency:

```toml
pyarnes_swarm = { git = "https://github.com/Cognitivemesh/pyarnes.git", rev = "{{ pyarnes_ref }}" }
```

The `[tool.pyarnes-tasks]` block is pre-wired with sensible defaults so `uv run tasks check` works from minute one — no manual configuration required.

`enable_dev_hooks` defaults to `true` when `adopter_shape=rtm-toggl-agile` and `false` for all other shapes. See [Enabling hooks in a Copier scaffold](#enabling-hooks-in-a-copier-scaffold) for the full `enable_dev_hooks` YAML block.

#### Shape: `pii-redaction` (content processing)

**Purpose:** PDF → text extraction → PII detection → redaction → markdown → TF-IDF keyword extraction.

Generated layout (under `src/{project_module}/`):

- `cli.py` — Typer app with `ingest <path>` and `redact <path>` subcommands.
- `pipeline.py` — `async def redact(input_path, *, title, allowed_roots)`. Builds `ToolRegistry` once, composes `GuardrailChain([PathGuardrail, ToolAllowlistGuardrail, PiiLeakGuardrail])`, dispatches tools inline so readers see the three-part contract (register → compose → dispatch) without a helper hiding it.
- `tools/__init__.py` — four `ToolHandler` subclasses: `ExtractText` (Kreuzberg wrapper), `DetectPii` (regex allowlist + optional Presidio), `RedactPii`, `RenderMarkdown`.
- `guardrails.py` — `PiiLeakGuardrail(Guardrail)` that refuses tool calls whose arguments contain PII-shaped strings; scrubs before `ToolCallLogger` persists them.
- `tests/test_redaction.py` — feeds a document with known PII and asserts the output contains none; exercises the `ToolAllowlistGuardrail` rejection path.

Runtime deps stamped by template: `kreuzberg`, `presidio-analyzer`, `presidio-anonymizer==2.2.354`, `spacy`, `scikit-learn`, `typer`.

**Design rationale:**

- `build_registry(...)` runs **once** per pipeline call and is threaded into `build_guardrail_chain(registry, allowed_roots=…)`. An earlier draft built three registries per call — rolled back during the simplify pass.
- Every `ToolHandler` subclass body stays under 30 lines; the `pyarnes_swarm` surface carries the weight.
- `GuardrailChain.check(tool, args)` is called **explicitly** in `pipeline.py` dispatch, reinforcing the "`AgentLoop` does not auto-apply guardrails" contract.
- Presidio is an optional runtime dep. The default shape ships a regex-allowlist stub so generated project tests pass on `uv sync --only-dev` without downloading the Presidio model.

#### Shape: `s3-sweep` (destructive infra)

**Purpose:** List S3 bucket → download all objects → verify each → **only then** delete the bucket. The verification gate is the entire point of the shape.

Generated layout (under `src/{project_module}/`):

- `cli.py` — Typer app with `download`, `verify`, `sweep` subcommands. Builds `ToolRegistry` once and threads it through all three stages so `FakeS3` fixture state persists.
- `pipeline.py` — `download`, `verify`, `sweep` accept an optional pre-built `registry`; each stage composes its own step against the shared registry.
- `tools/__init__.py` — `ListObjects`, `DownloadObject`, `VerifyObject` (size + etag), `WriteManifest`, `DeleteBucket`.
- `guardrails.py`:
  - `VerificationCompleteGuardrail` — reads the manifest; blocks `delete_bucket` if any entry is unverified. Raises `UserFixableError` with the diff of failing keys.
  - `BucketAllowlistGuardrail` — blocks any S3 tool targeting a bucket outside the allowlist.
- `fakes.py` — in-memory `FakeS3` so the generated project is green before a real boto3 account is wired in.
- `tests/test_pipeline.py` — happy path (download → verify → sweep); adversarial path (corrupt the manifest, assert `UserFixableError`).

Runtime deps stamped by template: `boto3`, `aioboto3`, `typer`.

**Design rationale:**

- **Tool-registry single source of truth.** `cli.py` calls `build_registry(s3=s3)` and passes the result into all three pipeline stages. Prevents the N+1 registry rebuild that an earlier draft produced.
- **Per-stage logging via `ToolCallLogger`.** Instantiated in `cli.py`, passed into each stage. The JSONL stream at `.pyarnes/tool_calls.jsonl` records every `download_object` + `verify_object` **before** any `delete_bucket` — an ordering invariant a feature test can assert.
- **No real-S3 dependency in-tree.** The generated project ships `FakeS3` so `uv run pytest` passes offline. Swapping to real boto3 is a one-line change in `cli.py` that replaces `FakeS3()` with an `aioboto3.client("s3")` wrapper.

#### Shape: `rtm-toggl-agile` (dual-use)

**Purpose:** Connect to `rememberthemilk.com` + `toggl.com`, download tasks/time entries, normalise into a shared schema, push into a unified agile backend (stories, sprints, WIP limits, time tracking tied to stories).

Generated layout (under `src/{project_module}/`):

- `cli.py` — Typer: `sync-rtm`, `sync-toggl`, `promote`.
- `pipeline.py` — builds the registry + chain; each stage dispatches through the shared `GuardrailChain`.
- `tools/__init__.py` — `ListRtmTasks`, `FetchRtmTask`, `ListTogglEntries`, `FetchTogglProject`, `CreateStory`, `LinkTimeEntry`, `PromoteToSprint`.
- `schema.py` — Pydantic models for the shared schema (story, time entry, tag, sprint, `AgileWorkspace`).
- `guardrails.py`:
  - `ApiQuotaGuardrail` — rate-limits RTM/Toggl calls per minute using a sliding window backed by `collections.deque` + `popleft` for O(1) amortised prune. Construct once in `pipeline.py` and reuse across every stage — constructing a fresh guardrail per dispatch resets the sliding window, a subtle bug the tests must exercise.
  - `SecretScanGuardrail` — rejects tool args or results matching credential patterns (`api_key=…`, `Bearer …`, `sk-…`) before they're persisted by `ToolCallLogger`. If a credential-shaped value reaches a tool's arguments, the chain raises `UserFixableError` before `ToolCallLogger` sees it; the audit trail therefore never contains secrets by construction.
- `tests/test_schema.py`, `tests/test_guardrails.py` — lossless round-trips and guardrail adversarial paths.

Runtime deps stamped by template: `httpx`, `pydantic`, `typer`.

**Design rationale:** This shape is the "meta-use" twist — `pyarnes_swarm` appears twice: once as the shipped runtime (same pattern as `pii-redaction` and `s3-sweep`) and again as the dev-time harness that governs the coding agent building the product. The template ships `RtmFixture` and `TogglFixture` classes the generated `cli.py` wires to each tool handler; adopters swap in real `httpx` clients with a one-line change. Keeps the generated project green on `uv sync` with no secrets or network access.

#### Dev-time hooks — `template/.claude/hooks/`

When `enable_dev_hooks=true` (default for `rtm-toggl-agile`, opt-in for other shapes), the template additionally stamps:

- `template/.claude/hooks/pyarnes_pre_tool.py.jinja` — organism wrapper around a `GuardrailChain`. The atoms are `PathGuardrail`, `CommandGuardrail`, `SecretLeakGuardrail`, `NetworkEgressGuardrail`, `RateLimitGuardrail`, and `ToolAllowlistGuardrail`; the chain is what the hook actually executes.
- `template/.claude/hooks/pyarnes_post_tool.py.jinja` — organism that composes three atoms in sequence: `ToolCallLogger`, `SecretLeakGuardrail`, and the flat `Budget` counter file. This is intentionally separate from lifecycle checkpointing.
- `template/.claude/hooks/pyarnes_stop.py.jinja` — narrow organism that reads the flat budget file and emits the Claude Code stop decision.
- `template/.claude/hooks/pyarnes_session_start.py.jinja` — lifecycle restore organism built on `Lifecycle.load()`.
- `template/.claude/hooks/pyarnes_session_end.py.jinja` — lifecycle persist organism built on `Lifecycle.dump()` plus the merged budget snapshot.
- `template/.claude/settings.json.jinja` — the final assembly point that registers all five organisms with Claude Code.
- `template/tests/bench/test_agent_quality.py.jinja` — agent-quality bench scaffold: defines `DiffSimilarityScorer` and `TestsPassScorer` locally (~20 lines each), loads labelled scenarios from `tests/bench/scenarios/*.yaml`, runs the coding agent over each scenario's workspace, and asserts `suite.summary()["pass_rate"] >= 0.80`.

#### Cross-shape invariants

- Every shape uses only the `pyarnes_swarm` stable API surface. No private submodule access.
- `GuardrailChain` is composed as a Python object — never deserialised from YAML/TOML. This is the non-negotiable design constraint that rules out a generic `pyarnes run --config pipeline.yaml` front end.
- `ToolCallLogger` is instantiated once per CLI invocation, not per tool call, so a single pipeline run produces one JSONL stream for the auditor.
- Scaffold tests (`tests/template/test_scaffold.py`) parametrise over all four shapes and must pass for each. `tests/template/test_dev_hooks.py` validates the rendered dev-hook files.

### Guardrail Implementation Patterns

Implementation of Guardrails must explicitly balance O(1) performance profiles against comprehensive runtime filtering. Two common practical patterns:

1. **`ApiQuotaGuardrail` Sliding-window Deque:**
To track rate-limits efficiently over time windows, avoid sorting or heavy timestamp aggregation. Instead, use Python's `collections.deque` restricted to a sliding time window (thus providing O(1) pruning on appending older timestamps).

2. **`SecretScanGuardrail` Pre-dispatch Redaction:**
To prevent accidental token leakage inside prompts (before they reach the `ModelRouter`), intercept parameters in the `pre_dispatch` hook hook and use regex pattern matchers like:
```python
CREDENTIAL_REGEX = re.compile(r"(?i)(bearer|token|key|secret|sk-)[^\s=:'\"]*[\s=:'\"]+([\\w-]{20,})")
```
Scrub all matched variables off the payload strictly prior to logging or network dispatch.
