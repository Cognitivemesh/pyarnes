# claudecode-pyarnes-judge-plugin

Status: **Deferred — not implemented.**

Design-only record for a future Claude Code plug-in that wraps the
`pyarnes-bench` RACE and FACT evaluators so they can be invoked from
inside a Claude Code session (manually via skills, automatically via
a `SubagentStop` hook). Authored alongside PR 2 so the shape is
fixed; no code under `plugin/` is created in this iteration.

The library layer (`RaceEvaluator`, `FactEvaluator`,
`RaceScore`, `FactMetrics`) is **sufficient** to build this plug-in
with zero library changes when the time comes.

## Motivation

Adopters using Claude Code day-to-day want two things the library
alone cannot offer:

1. **Skill-level access** — score a finished report from the slash-
   command palette without dropping into Python.
2. **Automatic scoring** — when a research subagent finishes, score
   the final assistant message inline so the user sees a quality
   number before they accept the result.

Both are packaging problems, not library problems. The evaluators are
already post-hoc and sequential; what is missing is a skill + hook
wrapper that speaks Claude Code's conventions.

## Scope

**Will ship (when implemented).**

- One plug-in manifest: `.claude-plugin/plugin.json`.
- Two skills: `race-evaluate` and `fact-check`, exposed as
  `/pyarnes-judge:race-evaluate` and `/pyarnes-judge:fact-check`.
- One hook: `hooks/hooks.json` registering a `SubagentStop` handler
  with a narrow matcher (`Explore|Research|general-purpose`).
- A ~20-line `ClaudeCliJudge` subprocess adapter implementing
  `ModelClient` via `claude -p`.
- A ~60-line argparse CLI entry point (`_judge_entry.py`) that wires
  the judge into `RaceEvaluator` / `FactEvaluator` and emits the
  result as JSON.
- A thin shell wrapper (`evaluate-report.sh`) invoked by skills and
  the hook.

**Will not ship.**

- No MCP server.
- No custom slash-command file (Claude Code already auto-maps skill
  names to `/pyarnes-judge:<skill>`).
- No top-level agent.
- No duplicated scoring, weighting, citation, or aggregation logic —
  the plug-in's Python is adapter + CLI glue only.
- No `anthropic` Python SDK. No `ANTHROPIC_API_KEY` requirement. No
  HTTP client.

## Planned file layout

```
plugin/pyarnes-judge/
  .claude-plugin/
    plugin.json                    # manifest
  skills/
    race-evaluate/SKILL.md         # /pyarnes-judge:race-evaluate
    fact-check/SKILL.md            # /pyarnes-judge:fact-check
  hooks/
    hooks.json                     # SubagentStop registration
  bin/
    _claude_cli_judge.py           # ~20 LOC ModelClient via `claude -p`
    _judge_entry.py                # ~60 LOC argparse CLI wiring
    evaluate-report.sh             # shell wrapper for skills + hook
  README.md                        # install + usage

tests/plugin/
  test_plugin_manifest.py          # validate manifest + SKILL frontmatter + hooks.json
  test_claude_cli_judge.py         # subprocess monkeypatched
  test_judge_entry.py              # CLI wired to a stub ModelClient
```

Total plug-in Python ≈ 80 LOC. No Gherkin (library BDD already covers
evaluator behaviour).

## Judge transport — `ClaudeCliJudge` via `claude -p`

The plug-in ships a ~20-line `ModelClient` adapter that shells out to
`claude -p '<prompt>' --model <id> --output-format json` via
`asyncio.create_subprocess_exec`, parses the `result` field, and
returns the payload shape the `pyarnes_bench._judge.judge_json` helper
expects.

Sketch:

```python
import asyncio
import json
import os
import shutil

from pyarnes_core.errors import TransientError, UserFixableError


class ClaudeCliJudge:
    def __init__(self, model: str = "sonnet") -> None:
        if shutil.which("claude") is None:
            raise UserFixableError(
                message="claude CLI not found; install Claude Code and ensure it is on PATH",
                prompt_hint="Install Claude Code (https://claude.com/code) or add it to PATH.",
            )
        self.model = os.environ.get("PYARNES_JUDGE_MODEL", model)

    async def next_action(self, messages):
        prompt = messages[-1]["content"]
        proc = await asyncio.create_subprocess_exec(
            "claude", "-p", prompt,
            "--model", self.model,
            "--output-format", "json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "PYARNES_JUDGE_INFLIGHT": "1"},
        )
        raw, err = await proc.communicate()
        if proc.returncode != 0:
            raise TransientError(
                message=f"claude -p exited {proc.returncode}: {err.decode()[:500]}",
            )
        return {"content": json.loads(raw)["result"]}
```

Justification:

- **Auth-agnostic.** `claude -p` inherits the user's Claude Code
  session (Anthropic API key, Claude Max subscription, Bedrock,
  Vertex). The plug-in never touches credentials.
- **No SDK dependency.** `uv run --with pyarnes-bench` pulls only
  `pyarnes-bench`; no `anthropic`, no `httpx` clients.
- **Reentrancy guarded.** `PYARNES_JUDGE_INFLIGHT=1` lets the hook
  detect an in-flight judge and short-circuit.

## Reuse contract

The plug-in's Python is exactly three things:

1. `ClaudeCliJudge` — Claude-Code-specific adapter that cannot live
   in a harness-agnostic library.
2. `_judge_entry.py` — argparse CLI that reads flags/stdin, constructs
   a `ClaudeCliJudge`, calls `RaceEvaluator` / `FactEvaluator` from
   `pyarnes_bench`, and emits the Pydantic result via
   `.model_dump_json()`.
3. Static JSON + Markdown (manifest, skills, hooks).

**No** duplicated scoring logic. **No** duplicated dataclasses.
**No** duplicated citation handling. If a behaviour change is needed
to RACE or FACT, it happens in the library and the plug-in inherits it
for free.

## Artifact flow

| Invocation                                        | Source of the report                         | How it reaches `_judge_entry.py`                                                                                       |
|---------------------------------------------------|----------------------------------------------|-------------------------------------------------------------------------------------------------------------------------|
| `/pyarnes-judge:race-evaluate <path>`             | File at `$ARGUMENTS`                         | Skill shell snippet passes `--mode race --report-path "$ARGUMENTS"` and prompts the user for `--reference-path`.       |
| `/pyarnes-judge:fact-check <path> <sources.json>` | File at `$ARGUMENTS`                         | Skill passes `--mode fact --report-path "$1" --sources-json "$2"`. `sources.json` is adopter-prepared.                 |
| `SubagentStop` hook                               | `last_assistant_message` from stdin payload  | `evaluate-report.sh` reads stdin, extracts with `jq`, pipes via `--report-stdin`. RACE only (FACT needs a sources map).|

## Reentrancy / recursion guard

The hook's command sets `PYARNES_JUDGE_INFLIGHT=1` before invoking
`claude -p`; `_judge_entry.py` checks this at start-up and exits
silently when set, so nested `SubagentStop` events never re-enter the
evaluator.

## Error mapping

| Error type                                            | Exit code |
|-------------------------------------------------------|-----------|
| `UserFixableError` (e.g. `claude` not on PATH)        | 2         |
| `LLMRecoverableError`                                 | 3         |
| `TransientError`                                      | 4         |
| `UnexpectedError` or any other exception              | 5         |

Exit 0 is reserved for success.

## Environment-variable knobs

| Env var                      | Purpose                                                                                  | Default     |
|------------------------------|------------------------------------------------------------------------------------------|-------------|
| `PYARNES_JUDGE_MODEL`        | Which Claude model the `ClaudeCliJudge` passes to `claude -p --model`                    | `sonnet`    |
| `PYARNES_JUDGE_INFLIGHT`     | Reentrancy guard set by the hook; checked at `_judge_entry.py` start-up                  | unset       |

## Illustrative examples

**`.claude-plugin/plugin.json`:**

```json
{
  "name": "pyarnes-judge",
  "version": "0.1.0",
  "description": "Post-hoc RACE and FACT evaluation of reports produced in a Claude Code session.",
  "author": { "name": "Cognitivemesh", "url": "https://github.com/cognitivemesh/pyarnes" },
  "homepage": "https://github.com/cognitivemesh/pyarnes",
  "repository": { "type": "git", "url": "https://github.com/cognitivemesh/pyarnes" },
  "license": "MIT"
}
```

**`skills/race-evaluate/SKILL.md`:**

```markdown
---
name: race-evaluate
description: Score a finished research report against a reference report using the RACE framework (4 dimensions, LLM-as-judge). Use when the user asks to grade, compare, or RACE-score a report file.
---

Run the library-backed evaluator on the report path the user provided:

    bash "$CLAUDE_PLUGIN_ROOT/bin/evaluate-report.sh" \
      --mode race \
      --report-path "$ARGUMENTS" \
      --reference-path "<ask the user for the reference path>"

Then summarise the JSON result: final_score, per-dimension weights, and any warnings.
```

**`skills/fact-check/SKILL.md`:**

```markdown
---
name: fact-check
description: Check citation trustworthiness of a finished report using the FACT framework (Accuracy + Effective Citations). Requires a JSON file mapping URL → fetched content.
---

The user will provide two args: `<report.md> <sources.json>`.

    bash "$CLAUDE_PLUGIN_ROOT/bin/evaluate-report.sh" \
      --mode fact \
      --report-path "$1" \
      --sources-json "$2"

Summarise the JSON result: citation_accuracy, effective_citations, supported/total claim counts.
```

**`hooks/hooks.json`:**

```json
{
  "hooks": {
    "SubagentStop": [
      {
        "matcher": "Explore|Research|general-purpose",
        "hooks": [
          { "type": "command", "command": "bash $CLAUDE_PLUGIN_ROOT/bin/evaluate-report.sh --mode race --report-stdin", "timeout": 120 }
        ]
      }
    ]
  }
}
```

## Installation and in-session usage

```text
# One-time install, inside any Claude Code session:
/plugin install https://github.com/cognitivemesh/pyarnes path:plugin/pyarnes-judge

# Manual RACE:
/pyarnes-judge:race-evaluate ./reports/q1-supply-chain.md
#   -> Claude prompts for a reference path, then returns a tool-result
#      block with the RaceScore JSON (per-dimension weights,
#      final_score in [0, 1]) and a human summary.

# Manual FACT (requires a pre-fetched sources map):
/pyarnes-judge:fact-check ./reports/q1-supply-chain.md ./reports/q1-sources.json

# Automatic: Explore/Research/general-purpose subagents trigger the
# SubagentStop hook, which pipes last_assistant_message through
# evaluate-report.sh --mode race --report-stdin.
```

## Testing plan (when implemented)

- `tests/plugin/test_plugin_manifest.py` — validate `plugin.json`
  schema, SKILL frontmatter presence, `hooks.json` shape
  (`matcher` + `SubagentStop` key).
- `tests/plugin/test_claude_cli_judge.py` — monkeypatch
  `asyncio.create_subprocess_exec` to a fake returning a canned
  `{"result": "..."}` payload; assert the judge
  - calls `claude` with `-p --model … --output-format json`,
  - raises `TransientError` on non-zero exit,
  - raises `UserFixableError` when `claude` isn't on PATH.
- `tests/plugin/test_judge_entry.py` — run `_judge_entry.py` with a
  stubbed `ModelClient` swapped in at import-time; assert exit codes
  and stdout JSON shape for both `race` and `fact` modes.

No Gherkin — the library BDD already covers evaluator behaviour; the
plug-in tests only exercise plumbing.

## Open questions

- Should `PYARNES_JUDGE_MODEL` default be `haiku` for cost-conscious
  defaults, or `sonnet` for quality? **Lean:** `sonnet` — the judge
  verdict is the whole point; 80 % of the plug-in's value evaporates
  with a weak judge.
- Should the hook also fire for non-research subagents? **Lean:** no —
  hook noise is the fastest way to get a plug-in uninstalled. Narrow
  matcher first; adopters can widen in their own overrides.
- Should we ship a `sources-fetch` helper skill (opt-in) to materialise
  `sources.json` automatically? **Lean:** out of scope here. Belongs in
  a separate plug-in if it ever ships, to preserve the "no URL fetching
  in pyarnes-bench" invariant.

## Status

Not implemented. This document exists so that when the plug-in is
built, the shape is already fixed and no library changes are required.
The library surface (`RaceEvaluator`, `FactEvaluator`, `RaceScore`,
`FactMetrics`) already meets every need this plug-in will have.
