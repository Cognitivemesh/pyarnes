---
persona: maintainer
level: L2
tags: [reference, mcp, graph]
---

# MCP tools (optional)

When a scaffolded project opts into the `enable_code_graph` Copier question, the generated `.claude/mcp.json` wires [`code-review-graph`](https://github.com/tirth8205/code-review-graph)'s MCP server into Claude Code. That server exposes **28 MCP tools** for incremental code-graph queries and blast-radius analysis, dramatically reducing the context your agent must read to understand a change.

## When to use it

- **Before a large refactor** — ask the agent for the blast radius of the function you are about to change.
- **During PR review** — surface which files are affected by a diff.
- **For onboarding** — let the agent explain the monorepo by walking its dependency graph instead of reading every `__init__.py`.

## Installation

The tools ship as opt-in:

```bash
uv sync --group graph         # install code-review-graph + graphifyy
```

For scaffolded projects, answer `yes` to `enable_code_graph` at `uvx copier copy …` time; Copier writes `.claude/mcp.json` pointing at the server.

## Listing the tools

From any terminal with the `graph` group installed:

```bash
uvx code-review-graph list-tools
```

The server's tool catalogue is maintained upstream — see the [code-review-graph README](https://github.com/tirth8205/code-review-graph) for the current list. Common categories:

| Category | Example tools | What they do |
|---|---|---|
| Graph build & refresh | `index`, `refresh`, `watch` | Build or incrementally update the SQLite graph for the current repo |
| Blast radius | `blast`, `impact`, `reverse-deps` | Show which callers / files are affected by a change |
| Semantic search | `search`, `nearest` | Find code by meaning, not just by name |
| Export | `export-graphml`, `export-cypher`, `export-obsidian` | Snapshot the graph for external visualization |
| Community detection | `communities`, `architecture` | Group related code into implicit modules |

## Running without MCP

The CLI side works standalone too — `uv run tasks graph:blast <path>` and `uv run tasks graph:render` are wired in `packages/tasks/src/pyarnes_tasks/cli.py` and run from any terminal in the monorepo.

## See also

- [Extension workflow — Optional graph tools](../maintainer/extend/workflow.md#optional-graph-tools) — how maintainers use these from the task runner.
- [Scaffold a project](../adopter/bootstrap/scaffold.md) — how adopters opt in at scaffold time.
