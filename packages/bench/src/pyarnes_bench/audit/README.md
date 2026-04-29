# pyarnes_bench.audit

In-tree, LLM-free, Python-only code-graph + audit subpackage. Replaces the
removed `graphify` and `code-review-graph` integrations.

## Surface

- `build_graph(...)` → tree-sitter-python parser walks the configured roots and
  returns a `networkx.DiGraph` with module / class / function / method nodes
  and `CONTAINS` / `IMPORTS` / `IMPORTS_FROM` / `CALLS` / `INHERITS` edges.
- `save_graph(g, path)` / `load_graph(path)` — atomic JSON persistence
  (`.pyarnes/audit/graph.json` by default) so the graph can be queried weeks
  later without re-parsing source.
- `god_nodes(g)`, `surprising_connections(g)`, `suggested_questions(g)` —
  cheap structural analyses (networkx stdlib, no `graspologic`).
- `audit_graph(g, ...)` → eight detectors:
  unused files, unused exports, unused dependencies, circular imports,
  duplicate function bodies, complexity hotspots, boundary violations,
  feature-flag usage.
- `AuditConfig.load(project_root)` reads `[tool.pyarnes-audit]` from
  `pyproject.toml`.
- Typed audit events (`log_audit_indexed`, `log_audit_analyzed`,
  `log_audit_finding`) emit JSONL through `pyarnes_core.observability`.

## CLI

| Task                 | What it does                                                    |
|----------------------|-----------------------------------------------------------------|
| `tasks audit:build`  | Parse, build the graph, persist to `.pyarnes/audit/graph.json`. |
| `tasks audit:show`   | Human-readable summary of the persisted graph.                  |
| `tasks audit:analyze`| God nodes, surprising connections, suggested questions.         |
| `tasks audit:check`  | All eight detectors; non-zero exit on HIGH findings.            |

## Phase 2 (deferred)

Opt-in extras within the same subpackage:

- `pyarnes-bench[audit-mvcc]` — libsql persistence.
- `pyarnes-bench[audit-leiden]` — Leiden communities via `graspologic`.
- `pyarnes_bench.audit.report` — Jinja2 markdown report.
- `pyarnes_bench.audit.mcp` — stdio MCP server.
- `pyarnes_bench.audit.viz` — single-file `graph.html`.

See `specs/consolidation/20-graph-package.md` for the full two-phase plan.
