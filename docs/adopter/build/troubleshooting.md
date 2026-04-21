---
persona: adopter
tags: [adopter, build, troubleshooting, faq]
---

# Troubleshooting

## `uv` can't find Python 3.13

Install 3.13 first, then re-sync:

```bash
uv python install 3.13
uv sync
```

If your system Python is pinned by policy, set `UV_PYTHON` to the managed interpreter path.

## First `uv sync` fails offline

The first sync needs network access to resolve and download wheels. Run it once on a connected machine (or CI cache), then use the populated cache for offline environments.

## `uv run tasks update` fails without `.copier-answers.yml`

`tasks update` needs Copier answers to know what to re-apply. If this file is missing, restore it from version control (or regenerate by re-scaffolding and copying the answers).

## Copier merge conflicts during update

Conflicts are expected when local changes overlap template changes. Resolve conflict markers manually, keep your project-specific edits, then re-run tests and docs build.

## Import errors when guardrails are not wired

pyarnes does not auto-apply guardrails. If your wrappers are missing, you may see unresolved imports for custom guarded wrappers or direct tool execution without checks. Wire a `GuardrailChain` through your tool registration path (see [Quick start](quickstart.md#5-integrate-guardrails-into-the-loop)).

## `mkdocs build --strict` fails on missing nav targets

Strict mode fails when `mkdocs.yml` points to files that do not exist (or moved paths). Verify each nav target path under `docs/`, and keep redirects/nav entries in sync when renaming pages.
