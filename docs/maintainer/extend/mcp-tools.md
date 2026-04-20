---
persona: maintainer
tags: [maintainer, extend, mcp, graph]
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

The exact tool names and signatures live in the [code-review-graph README](https://github.com/tirth8205/code-review-graph) and evolve upstream. Typical capabilities include: building/refreshing an incremental code graph, querying the blast radius of a file or function, semantic search across the repo, exporting to GraphML / Neo4j Cypher / Obsidian, and community detection for implicit modules. Run `uvx code-review-graph list-tools` for the authoritative list in your pinned version.

## Running without MCP

The CLI side works standalone too — `uv run tasks graph:blast <path>` and `uv run tasks graph:render` are wired in `packages/tasks/src/pyarnes_tasks/cli.py` and run from any terminal in the monorepo.

## See also

- [Extension workflow — Optional graph tools](workflow.md#optional-graph-tools) — how maintainers use these from the task runner.
- [Scaffold a project](../../adopter/bootstrap/scaffold.md) — how adopters opt in at scaffold time.
