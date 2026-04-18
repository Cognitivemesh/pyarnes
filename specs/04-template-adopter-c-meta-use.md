# 04 — Shape reference: rtm-toggl-agile, and meta-use dev hooks

## Context

The `rtm-toggl-agile` shape is the plan's key twist: pyarnes appears *twice* in the adopter project. Once as the shipped runtime (same pattern as `pii-redaction` and `s3-sweep` in Spec 03) and **again as the dev-time harness that tracks, gates, and scores the coding agent itself** while the adopter's team builds the product.

This spec covers both halves:

1. The `rtm-toggl-agile` shape — the shipped pipeline: RTM + Toggl → normalise → unified agile workspace.
2. Dev-time hooks in `template/.claude/hooks/` that adopters opt into. The hooks import `pyarnes_core`, `pyarnes_guardrails`, and `pyarnes_harness` to harness the coding agent during development.

The plan's "Meta-use" table maps every pyarnes package to a dev-time use. This spec turns that table into template-stamped files.

**Earlier draft note.** An earlier iteration shipped the shape as a full `packages/example-rtm-toggl-agile/` in-tree workspace. That copy was retired along with `example-pii-pipeline/` and `example-s3-sweep/` (see Spec 03's note). The shape is now delivered exclusively through the Copier template's `adopter_shape=rtm-toggl-agile` conditional blocks, with `tests/template/test_scaffold.py` + `tests/template/test_dev_hooks.py` validating the rendered output.

## Goals / Non-goals

**Goals**

- Document the `rtm-toggl-agile` shape with the same fidelity as Spec 03 (CLI, tools, guardrails, tests).
- Ship Claude Code `PreToolUse` and `PostToolUse` hooks that wire `GuardrailChain` + `ToolCallLogger` + `get_logger` into the coding agent's activity.
- A `tests/bench/test_agent_quality.py` scaffold driving `EvalSuite` across labelled coding scenarios with a minimum pass rate assertion.
- `.pyarnes/` directory layout: `.pyarnes/dev.jsonl` (session logs), `.pyarnes/agent_tool_calls.jsonl` (audit trail).
- Opt-in via Copier toggle `enable_dev_hooks` (default **on** when `adopter_shape=rtm-toggl-agile`, default **off** otherwise).

**Non-goals**

- Claude Code hook-protocol changes. Target the documented `PreToolUse` / `PostToolUse` interface as-shipped.
- New scorers beyond the plan's minimal set. Adopters extend.
- A labelled coding-scenarios corpus. Template ships 2 trivial fixtures; adopters grow their own.

## Shape: `rtm-toggl-agile`

**Purpose:** connect to `rememberthemilk.com` + `toggl.com`, download tasks/time entries, normalise into a shared schema, push into a unified agile backend (stories, sprints, WIP limits, time tracking tied to stories).

Generated layout (under `src/{project_module}/`):

- `cli.py` — Typer: `sync-rtm`, `sync-toggl`, `promote`.
- `pipeline.py` — builds the registry + chain; each stage dispatches through the shared `GuardrailChain`.
- `tools/__init__.py` — `ListRtmTasks`, `FetchRtmTask`, `ListTogglEntries`, `FetchTogglProject`, `CreateStory`, `LinkTimeEntry`, `PromoteToSprint`.
- `schema.py` — Pydantic models for the shared schema (story, time entry, tag, sprint, `AgileWorkspace`).
- `guardrails.py`:
  - `ApiQuotaGuardrail` — rate-limits RTM/Toggl calls per minute using a sliding window. Backed by `collections.deque` + `popleft` for O(1) amortised prune (replaced the list-rebuild the simplify review caught in an earlier draft).
  - `SecretScanGuardrail` — rejects tool args or results matching credential patterns (`api_key=…`, `Bearer …`, `sk-…`) before they're persisted by `ToolCallLogger`.
- `tests/test_schema.py`, `tests/test_guardrails.py` — lossless round-trips and guardrail adversarial paths.

Runtime deps the template adds: `httpx`, `pydantic`, `typer`.

### Design notes

- **Fixtures stand in for the real APIs.** The template ships `RtmFixture` and `TogglFixture` classes the generated `cli.py` wires to each tool handler. Adopters swap in real `httpx` clients with a one-line change. Keeps the generated project green on `uv sync` with no secrets or network.
- **`ApiQuotaGuardrail` is stateful.** Construct once in `pipeline.py`, reuse across every stage of a `promote` run. Constructing a fresh guardrail per dispatch would reset the sliding window — a subtle bug the shape's tests must exercise.
- **`SecretScanGuardrail` runs pre-dispatch.** If a credential-shaped value ever reaches a tool's arguments, the chain raises `UserFixableError` before `ToolCallLogger` sees it. The audit trail therefore never contains secrets by construction.

## Dev-time hooks (template)

**Files stamped only when `enable_dev_hooks=true`:**

- `template/.claude/hooks/pyarnes_pre_tool.py.jinja`
- `template/.claude/hooks/pyarnes_post_tool.py.jinja`
- `template/.claude/settings.json.jinja` — registers both hooks under `PreToolUse` / `PostToolUse`.
- `template/tests/bench/test_agent_quality.py.jinja` — agent-quality bench scaffold.

### Pre-tool-use hook

Composes `PathGuardrail(allowed_roots=(repo_root,))`, `CommandGuardrail()`, and `ToolAllowlistGuardrail(allowed_tools=frozenset({"Read", "Write", "Edit", "Glob", "Grep", "Bash", "TodoWrite"}))`. Reads the Claude Code JSON event from stdin, calls `CHAIN.check(tool_name, tool_input)`, and:

- On `UserFixableError`, prints `{"decision": "block", "reason": ...}` to stdout and `sys.exit(2)` — the Claude Code hook protocol's block signal.
- Otherwise `sys.exit(0)`, allowing the tool call.

The hook imports from the top-level `pyarnes_guardrails` and `pyarnes_core.errors` — no private submodule access. This was tightened in the simplify pass (an earlier draft reached into `pyarnes_harness.capture` for `ToolCallLogger`; now uses the top-level re-export).

### Post-tool-use hook

Instantiates a `ToolCallLogger(path=".pyarnes/agent_tool_calls.jsonl")`, reads the Claude Code event, computes `duration_seconds = finished_at - started_at`, and calls `logger.log_call(...)`. The hook always exits 0 — post-tool-use hooks must never block the agent.

### `.pyarnes/` directory contract

- `.pyarnes/dev.jsonl` — structured logs from `get_logger("coding_agent.*")`.
- `.pyarnes/agent_tool_calls.jsonl` — `ToolCallLogger` output.
- `.pyarnes/.gitignore` — `*.jsonl`.

### Agent-quality bench

`template/tests/bench/test_agent_quality.py.jinja`:

- Defines `DiffSimilarityScorer` and `TestsPassScorer` locally (~20 lines each). Upstreaming to `pyarnes-bench` is deferred until a second adopter needs them.
- Loads labelled scenarios from `tests/bench/scenarios/*.yaml`.
- Runs the coding agent over each scenario's workspace, collects `EvalResult`s into an `EvalSuite`, asserts `suite.summary()["pass_rate"] >= 0.80`.

### Copier integration

```yaml
enable_dev_hooks:
  type: bool
  help: Wire pyarnes into Claude Code hooks to harness the coding agent during development?
  default: "{{ adopter_shape == 'rtm-toggl-agile' }}"
```

The `_exclude` block in `copier.yml` gates every dev-hook file on this flag so shapes that opt out generate no `.claude/hooks/`, `.claude/settings.json`, or `tests/bench/`.

## Tests / acceptance

- `tests/template/test_scaffold.py::test_dev_hooks_ship_only_when_enabled` — renders `blank` without the toggle and `rtm-toggl-agile` with `enable_dev_hooks=True`; asserts the two hook files, `settings.json`, and `tests/bench/` appear in the latter and not the former.
- `tests/template/test_dev_hooks.py::test_pre_tool_hook_blocks_command_guardrail` — runs `pyarnes_pre_tool.py` as a subprocess against a synthetic `rm -rf /` event; asserts exit code 2 and the `{"decision": "block", …}` payload.
- `tests/template/test_dev_hooks.py::test_pre_tool_hook_blocks_disallowed_tool` — same, with an unknown tool name.
- `tests/template/test_dev_hooks.py::test_pre_tool_hook_allows_safe_call` — asserts exit 0 for a `Read` under the project root.
- `tests/template/test_dev_hooks.py::test_post_tool_hook_appends_jsonl` — asserts one JSONL record with `tool`, `is_error`, and `duration_seconds == pytest.approx(0.5)` (round-trip check, not mere key presence).

## Open questions

- Do the custom scorers (`DiffSimilarityScorer`, `TestsPassScorer`) belong in `pyarnes-bench` (stable surface, Spec 01 would need updating) or stay as adopter code? Leaning adopter-code until a second adopter needs them.
- Should hook scripts self-update via `uv run tasks update` when the template evolves? Probably yes — covered by Copier `_migrations`; defer concrete design.
- `ToolAllowlistGuardrail` lists tool names as strings. A shared constants module could catch typos but would couple pyarnes to Anthropic's tool-name contract. Defer.
- Windows/PowerShell `sys.exit(2)` block semantics: Claude Code hook docs confirm exit code 2 blocks on all platforms; re-verify on a fresh release cadence.

Next: `05-docs-distribution-and-meta-use.md`.
