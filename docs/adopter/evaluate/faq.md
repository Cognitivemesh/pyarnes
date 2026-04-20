---
persona: adopter
level: L1
tags: [adopter, evaluate, faq, troubleshooting]
---

# FAQ & troubleshooting

The errors below are the most common stumbles when bootstrapping a pyarnes-based project. Each entry lists the symptom, the root cause, and the fix.

## Installation

### `uv` cannot find Python 3.13

**Symptom.** `uv sync` fails with `No interpreter found for Python >=3.13`.

**Cause.** pyarnes targets Python 3.13+ (see `requires-python` in every package's `pyproject.toml`). Older interpreters cannot satisfy the workspace constraint.

**Fix.** Install a compatible interpreter through `uv` itself — no system package manager required:

```bash
uv python install 3.13
uv sync
```

### First `uv sync` fails without network

**Symptom.** `uv sync` errors with `Could not resolve host` or a timeout.

**Cause.** `uv sync` fetches the dependency closure from PyPI the first time it runs. With no cache and no network, it cannot proceed.

**Fix.** Run `uv sync` once on a connected machine to populate `~/.cache/uv`, then copy the cache to the offline machine, or pre-build a wheelhouse with `uv pip compile` + `uv pip download` and point the offline workspace at it via `UV_INDEX_URL`.

## Scaffolding

### `uv run tasks update` fails when `.copier-answers.yml` is missing

**Symptom.** `Could not find .copier-answers.yml`.

**Cause.** `update` re-runs the Copier template against an existing project to pull in new upstream changes. It keys off the answers file that was written at scaffold time. If the file was deleted, renamed, or the project was hand-created without Copier, there is nothing to diff against.

**Fix.** Either restore the file from git history (`git show HEAD:.copier-answers.yml > .copier-answers.yml`) or, for projects created outside Copier, run a fresh scaffold into a sibling directory with matching answers and merge the result manually. See [scaffold.md § "Updating an existing project"](../bootstrap/scaffold.md) for details.

### Merge conflicts from `copier update`

**Symptom.** After `uv run tasks update`, files show `<<<<<<< HEAD` markers.

**Cause.** The upstream template changed a file that you also edited locally. Copier does not silently drop your edits — it surfaces them as merge conflicts.

**Fix.** Resolve each conflict as you would a normal git merge. For template-owned files you did not mean to edit (`pyproject.toml` lockable sections, CI config), prefer the upstream side (`git checkout --theirs <file>`). For project-owned files you customized (`README.md`, your tool code), prefer yours (`git checkout --ours <file>`) and re-apply any template improvements by hand.

## Running the loop

### "Unknown tool: " result appears in messages

**Symptom.** A `tool`-role message arrives with content `"Unknown tool: "` (empty tool name).

**Cause.** The model returned an action dict that the loop could not classify — typically a missing `type` field, a `type` not in `{"tool_call", "final_answer"}`, or a `tool_call` with an empty `tool` string.

**Fix.** The loop now routes these through `ActionKind.UNKNOWN` and returns an error `ToolMessage` so the model can self-correct (see `packages/harness/src/pyarnes_harness/loop.py:160-168`). If you see this repeatedly from the same model, your `next_action` implementation is probably dropping the `type` field or miscategorizing the response — re-check the mapping in your `ModelClient` (see the [Anthropic SDK worked example](../build/quickstart.md#worked-example-anthropic-sdk)).

### Retries take too long — or too few

**Symptom.** A `TransientError`-raising tool retries fewer times than expected, or a per-call backoff you set on the error is ignored.

**Cause.** Each `TransientError` may override `max_retries` and `retry_delay_seconds`. The effective policy is `max(LoopConfig value, error value)` — tools can raise the cap but never lower it.

**Fix.** Either raise `LoopConfig.max_retries` for the whole loop, or raise a `TransientError(max_retries=5, retry_delay_seconds=3)` from inside the tool when you know a specific call needs more time.

## Guardrails

### My tool call is being blocked but the path looks fine

**Symptom.** `PathGuardrail` raises `UserFixableError` on a path that appears to be under `/workspace`.

**Cause.** Canonicalization (`..` collapsed, symlinks followed) resolves to somewhere outside the allowed roots. This is working as intended — see [security.md § Known limits](security.md#known-limits).

**Fix.** Print the canonical form before the call:

```python
from pathlib import Path
print(Path(arguments["path"]).resolve(strict=False))
```

If the resolved path is genuinely where you want it, add its *resolved* root to `allowed_roots`. If it is not, the guardrail just saved you.

### My command-taking tool is not being scanned

**Symptom.** `CommandGuardrail` lets a `"sudo rm -rf /"` call through.

**Cause.** Your tool accepts the command under a key that is not in `CommandGuardrail.command_keys`. The default set is `("command", "cmd", "argv", "script", "shell_command", "run")`.

**Fix.** Extend `command_keys` for your tool:

```python
CommandGuardrail(command_keys=("command", "cmd", "exec", "invoke"))
```

See [security.md § Known limits](security.md#default-command_keys-is-not-exhaustive).

## Logging

### The JSONL file has fields inside `message=...` instead of top-level keys

**Symptom.** A log line like `{"event": "loop.iteration iteration=0", ...}` rather than `{"event": "loop.iteration", "iteration": 0, ...}`.

**Cause.** You called `logger.info("text {field}", field=...)` directly. Loguru bakes format kwargs into `record["message"]`; the JSON serializer reads structured data from `record["extra"]`, not from the message.

**Fix.** Use the `log_event` / `log_warning` / `log_error` helpers from `pyarnes_core.observability`, which call `logger.bind(**fields).info(event)` so the fields land in the right place. See `packages/core/src/pyarnes_core/observability/bound_logger.py`.

## See also

- [Installation](../bootstrap/install.md)
- [Scaffold a project](../bootstrap/scaffold.md)
- [Security & threat model](security.md)
- [Error taxonomy](errors.md)
