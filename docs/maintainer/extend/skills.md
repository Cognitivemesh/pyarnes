---
persona: maintainer
level: L2
tags: [maintainer, extend, skills]
---

# Authoring template skills

pyarnes ships Claude Code skills via the Copier template so every scaffolded project gets them for free. This page is the maintainer-facing guide for adding, editing, and smoke-testing those shipped skills.

## Where skills live

```text
template/
└── .claude/
    └── skills/
        └── <skill-name>/
            └── SKILL.md
```

Anything under `template/.claude/skills/` is stamped into every scaffolded project **unchanged** (not Jinja-rendered — the filenames have no `.jinja` suffix). Adopters can then edit their local copy; pulling `uv run tasks update` merges template-side improvements.

## Current inventory

| Skill | Purpose |
|---|---|
| `python-test` | Scaffold pytest tests (unit or BDD) following pyarnes conventions. |

## Anatomy of a SKILL.md

See the SKILL.md anatomy block in [Adopter › Skills § Adding your own skills](../../adopter/build/skills.md#adding-your-own-skills). The authoring shape is the same; the only difference maintainer-side is the location (`template/.claude/skills/` so the skill ships into every scaffolded project, instead of a single project's `.claude/skills/`).

## Adding a new skill

1. Create `template/.claude/skills/<name>/SKILL.md`. Use the anatomy above.
2. If the skill needs ancillary files (scripts, templates it copies), put them in the same directory — they ship alongside the `SKILL.md`.
3. Document it in the inventory tables on **both** of:
   - `docs/adopter/build/skills.md` (what adopters see)
   - this page (what maintainers see)
4. Smoke-test via the procedure below.

## Smoke-testing a skill

Scaffold a throwaway project and invoke the skill inside it:

```bash
rm -rf /tmp/pyarnes-skill-smoke
uvx copier copy --defaults \
  --data project_name=skill-smoke \
  --data project_description=demo \
  "$(pwd)" /tmp/pyarnes-skill-smoke
cd /tmp/pyarnes-skill-smoke
ls .claude/skills/               # confirm the skill shipped
```

Then open the project in Claude Code and use one of the documented trigger phrases. Verify:

- The skill activates (Claude references it by name).
- The resulting files match conventions (imports, frontmatter, logging setup).
- `uv run tasks check` still passes on the modified project.

Full smoke-test details: [Evolving workflow § Smoke-testing the template](workflow.md#smoke-testing-the-template).

## Hazards / stable surface

- **Skill names and trigger phrases are observable contract.** Adopters have told Claude Code to use them. Renaming is a breaking change; add a `_migrations` entry in `copier.yml` if you must.
- **Never add Jinja templating to `SKILL.md`.** Skills should be identical across every scaffolded project — branching by Copier answer in the skill body means adopters see different skills based on their scaffold-time choices, which undermines "Claude Code knows what to do".
- **Don't add runtime dependencies.** Skills instruct Claude Code to use tools the scaffolded project already has — `uv run tasks`, stdlib, `pyarnes-*`. Pulling in new deps just because a skill wants them bloats every adopter's install.

## See also

- [`docs/adopter/build/skills.md`](../../adopter/build/skills.md) — the adopter-facing view.
- [Editing the Copier template](template.md) — full template-editing reference.
- [Evolving workflow](workflow.md) — the daily workflow that smoke-testing plugs into.
