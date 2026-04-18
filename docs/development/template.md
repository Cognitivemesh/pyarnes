# Evolving the Copier template

The Copier template lives under [`template/`](https://github.com/Cognitivemesh/pyarnes/tree/main/template)
and [`copier.yml`](https://github.com/Cognitivemesh/pyarnes/blob/main/copier.yml).
Every edit to either must keep both new scaffolds AND existing adopter
projects (running `uvx copier update`) green.

## Layout

- `template/<everything>.jinja` — files rendered into the adopter project.
- `template/src/{{project_module}}/` — source tree; `project_module` is a
  computed Copier variable derived from `project_name`.
- `template/.claude/hooks/*.jinja` — dev-time hooks; ship only when
  `enable_dev_hooks=true` via `_exclude` in `copier.yml`.
- `template/tests/bench/*.jinja` — agent-quality bench scaffolding; same
  conditional ship rule.

## Adding a new Copier question

1. Add a `<name>:` block to `copier.yml` under the "Prompts" section.
   Always give it a `default` so `--defaults` stays non-interactive.
2. Reference the new variable from `.jinja` files as `{{ <name> }}`
   (values) or `{% if <name> %}...{% endif %}` (conditionals).
3. Extend `tests/template/test_scaffold.py` with at least one
   parameterisation covering the new value.
4. Document the question in [`docs/template.md`](../template.md).

## Conditional files and directories

Copier supports two mechanisms for "ship this file only when X":

### `_exclude` globs with Jinja expressions (preferred)

```yaml
_exclude:
  - "{% if not enable_dev_hooks %}.claude/hooks{% endif %}"
  - "{% if not enable_dev_hooks %}.claude/hooks/**{% endif %}"
```

Exclude both the directory AND its `/**` contents — otherwise Copier
creates the empty directory.

### Filename templating (avoid)

`template/{% if X %}foo.py{% endif %}.jinja` works but: when `X` is
false, the filename evaluates to `.jinja` which Copier treats as an
almost-valid template. Use `_exclude` instead — failure modes are clearer.

## Testing template changes

The fast loop:

```bash
uv run pytest tests/template/ -v
```

This runs Copier's Python API against an in-process copy of the repo
(with `.git` stripped, since Copier's local-clone path fails under
`/tmp` hardlink semantics). It covers scaffold generation for each
`adopter_shape`, shape-specific deps, `enable_dev_hooks` gating, and the
subprocess hook behaviour when hooks are enabled.

For end-to-end validation against the real git URL flow:

```bash
git push origin main
uvx copier copy gh:Cognitivemesh/pyarnes /tmp/pyarnes-e2e
cd /tmp/pyarnes-e2e && uv sync && uv run tasks check
uvx copier update    # round-trip: should apply cleanly with no conflicts
```

## Breaking template changes

Copier supports `_migrations` in `copier.yml` for cross-version migrations.
Use it when:

- A template question is removed or its semantics change.
- A rendered file is renamed.
- Generated project structure moves in an incompatible way.

Ship the migration with a clear changelog entry; adopters running
`uv run tasks update` will see the migration run once and their project
will follow the new layout.

## What must stay stable

- `project_name`, `project_description`, `python_version`, `pyarnes_ref`,
  `project_module` as Copier variables. Adopters' existing
  `.copier-answers.yml` files depend on these names.
- The top-level directory structure adopters import from
  (`src/{{project_module}}/{pipeline,cli,tools,guardrails}.py`).
- The `[project.scripts]` entry point name deriving from `project_module`.

Changes to any of the above require a `_migrations` entry and a
coordinated release announcement.
