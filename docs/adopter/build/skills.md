---
persona: adopter
tags: [adopter, build, skills]
---

# Claude Code skills in your scaffolded project

When you bootstrap a project with `uvx copier copy gh:Cognitivemesh/pyarnes`, your `.claude/skills/` directory ships with skills the coding agent can invoke on demand. Skills are small Markdown files that teach Claude Code how to handle specific requests the way pyarnes conventions expect.

## Shipped skills

| Skill | Purpose | Trigger phrases |
|---|---|---|
| `python-test` | Scaffold pytest tests (unit or BDD) following pyarnes conventions — async-first, Red → Green → Refactor, loguru stderr logging. | "write a test for X", "add a test", "scaffold tests", "test this function", "how do I start testing here?" |

## How skills work

```mermaid
sequenceDiagram
    actor You
    participant Claude as Claude Code
    participant Skill as .claude/skills/&lt;name&gt;/SKILL.md
    participant Tools as Read/Write/Bash tools

    You->>Claude: "Write a test for ReadFileTool"
    Claude->>Claude: match trigger phrase
    Claude->>Skill: load SKILL.md
    Skill-->>Claude: instructions (scaffold tests/, write test file, follow conventions)
    Claude->>Tools: Write tests/unit/test_read_file.py
    Claude->>Tools: Write tests/conftest.py (if missing)
    Claude-->>You: "Test scaffolded — run uv run tasks test"
```

The `SKILL.md` frontmatter tells Claude Code which phrases activate the skill. The body tells it what to do once activated. No install step — the skill is just there in `.claude/skills/`.

## Using the python-test skill

After scaffolding your project and adding a module you want to test, just ask:

```
You: "Write a unit test for my ReadFileTool class in src/my_agent/tools.py"
```

The first time you invoke it, Claude Code will create the full `tests/` scaffold:

```
tests/
├── __init__.py
├── conftest.py              # configures loguru for test runs
└── unit/
    ├── __init__.py
    └── test_tools.py        # the first test
```

Subsequent invocations just add new test files next to the existing ones. Run:

```bash
uv run tasks test
```

## Adding your own skills

Create `.claude/skills/<skill-name>/SKILL.md` in your project:

```markdown
---
name: my-skill
description: One-line summary. Include the trigger phrases verbatim so Claude Code knows when to activate ("Use when the user asks to X, Y, or Z").
---

# my-skill — what it does

## When this skill activates

Typical user phrasings:

- "Do X"
- "Add a Y"
- …

## What the skill does

1. First step…
2. Second step…
```

Skills live alongside the code they touch — so when Copier updates your template, your own skills stay put.

## See also

- Canonical source of the shipped skill: [`template/.claude/skills/python-test/SKILL.md`](https://github.com/Cognitivemesh/pyarnes/blob/main/template/.claude/skills/python-test/SKILL.md)
- For pyarnes maintainers adding template-shipped skills: [Authoring template skills](../../maintainer/extend/skills.md)
