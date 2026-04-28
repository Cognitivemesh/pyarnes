# pyarnes_swarm — Graph Package (`pyarnes_graph`)

> **Spec header**
>
> | Field | Value |
> |---|---|
> | **Title** | pyarnes_swarm — Code-Review Graph Package (Optional Subsystem) |
> | **Status** | active |
> | **Type** | optional-subsystem |
> | **Owns** | pyarnes_graph package, three-table SQLModel schema, TreeSitter indexer pipeline, WhyComment extractor, graph-based scorers (TokenReductionScorer, LLMJudgeScorer), blast-radius and centrality analyses |
> | **Depends on** | 06-hook-integration.md, 07-bench-integrated-axes.md, 13-run-logger.md |
> | **Extends** | — |
> | **Supersedes** | PR-01-graph-package-foundation.md, PR-02-extractor-and-indexer.md, PR-03-analytics-and-report.md, PR-04-tools-mcp-and-hook.md, PR-05-eval-and-usage-tracking.md, PR-06-skills-template-docs.md |
> | **Read after** | 13-run-logger.md |
> | **Read before** | — |
> | **Not owned here** | runtime loop (see `04-swarm-api.md`); evaluation contracts — `Scorer` and `EvalResult` (see `07-bench-integrated-axes.md`); message-safety pipeline (see `20-message-safety.md`); external hook event-JSON contract (see `06-hook-integration.md`) |
> | **Last reviewed** | 2026-04-29 |

## Design Rationale

**Why a separate `pyarnes_graph` package instead of bundling into `pyarnes_swarm`?** The graph feature pulls in heavy optional dependencies — Tree-sitter grammars, NetworkX, Leiden via `graspologic` (numpy / scipy / numba), Jinja2, the MCP SDK, libsql drivers. Adopters who only want orchestration shouldn't pay that install cost. A separate workspace member lets `pyarnes_swarm` stay slim and lets graph users opt in via `pyarnes-graph` as an explicit dependency. The dependency direction is one-way: `pyarnes_graph` imports from `pyarnes_swarm` (`ModelClient`, `ToolHandler`, `Scorer`/`ScoreResult`, `ToolCallLogger`, `GuardrailChain`); `pyarnes_swarm` never imports from `pyarnes_graph`.

**Why Turso/libsql over stdlib `sqlite3`?** Indexing fires concurrent writes — multiple files parsed in parallel, the watcher reacting to edits while a CLI run is still flushing. Stdlib SQLite serialises writers even in WAL mode, so concurrent indexers contend on a single lock. Turso/libsql uses MVCC (the same technique as the message bus — see `02-message-bus.md`), so writers don't block each other. It is also async-native via `sqlalchemy-libsql`, which keeps the indexer fully `async` without thread-pool shims. Local file (`./.pyarnes/graph.db`) and hosted Turso use the same call signature.

**Why Tree-sitter for extraction?** Tree-sitter gives fast incremental parsing across many languages with one library and a uniform AST. We don't need to bundle language-specific tooling (`ast` for Python, `@babel/parser` for JS, `syn` for Rust) or maintain N parser frontends. v1 ships Python only; adding JS/TS/Rust/Go later means swapping the grammar, not rewriting the extractor.

**Why Leiden for community detection?** Louvain — the more famous algorithm — is known to produce poorly-connected communities (a node can end up in a community where it is barely connected to other members). Leiden fixes that defect: it guarantees every community is internally connected, and consistently finds smaller, more meaningful clusters in code-graph research. `graspologic.partition.leiden` is the default in their API and matches the architectural-clustering use-case directly.

**Why a Markdown report instead of letting the model query tools every time?** A single 2k-token report fits in any model's context and is cacheable. Tool calls cost a round-trip per query. The `GRAPH_REPORT.md` is the bulk-reduction lever — the PreToolUse hook injects it once, the model gets the structural overview "for free", and tool calls become targeted follow-ups rather than the only entry point. This is the mechanism that delivers the 5×–71× token-reduction target.

## Package overview

`pyarnes_graph` is a workspace member with this public surface:

```
pyarnes_graph/
├── schema.py               # NodeKind, EdgeKind, Confidence enums + GraphNode, GraphEdge, IndexMeta
├── store/
│   ├── engine.py           # async create_engine(db_path) → AsyncEngine (libsql or aiosqlite)
│   └── repository.py       # upsert_nodes, upsert_edges, upsert_index_meta, neighbors, get_node
├── builder/
│   ├── tree_sitter.py      # TreeSitterBuilder (Python AST → nodes + edges)
│   └── why_comments.py     # WhyCommentBuilder (# WHY/HACK/NOTE/TODO scanner)
├── indexer.py              # Indexer.index(root) / Indexer.watch(root) — SHA-256 incremental
├── analysis/
│   ├── graph_view.py       # build_nx(session, kinds, min_confidence) → nx.DiGraph
│   ├── blast_radius.py     # affected-symbol set via descendants/ancestors
│   ├── centrality.py       # betweenness + in-degree, "god node" composite score
│   ├── communities.py      # Leiden via graspologic
│   └── report.py           # GRAPH_REPORT.md generator (Jinja2, ~2k token cap)
├── tools/
│   ├── get_node_tool.py
│   ├── get_neighbors_tool.py
│   ├── shortest_path_tool.py
│   ├── blast_radius_tool.py
│   └── registry_factory.py # build_graph_registry(engine) → ToolRegistry
├── mcp/
│   └── server.py           # stdio JSON-RPC server (python -m pyarnes_graph.mcp.server)
├── hooks/
│   └── pretooluse.py       # PreToolUse hook entrypoint
├── templates/
│   └── graph_report.md.j2  # adopter-forkable Jinja2 report template
├── usage.py                # JSONL capture-log aggregator (graph:usage)
└── tasks.py                # graph:index, graph:watch, graph:report, graph:eval, graph:usage, graph:ci
```

`pyarnes_graph` reuses these primitives from `pyarnes_swarm` rather than re-implementing them: `get_logger` and JSONL stderr logging, `ToolHandler` ABC, `ToolRegistry`, `ToolCallLogger` / `CapturedOutput`, `Lifecycle` FSM, the error taxonomy (`TransientError`, `LLMRecoverableError`, `UserFixableError`, `UnexpectedError`), `GuardrailChain` plus `PathGuardrail` and `ToolAllowlistGuardrail`, and the `Scorer` / `ScoreResult` contract.

## Storage layer

Three SQLModel tables, one schema module:

- **`GraphNode`** — `id` (`"{relative_path}::{qualname}"`), `kind: NodeKind`, `name`, `file_path`, `sha256`, `confidence: Confidence`, `extra: dict` (JSON column).
- **`GraphEdge`** — `src_id`, `dst_id`, `kind: EdgeKind`, `confidence: Confidence`, `extra: dict`.
- **`IndexMeta`** — per-file row keyed by `file_path`: `sha256`, `parser_version`, `indexed_at`. Drives the incremental skip in the indexer.

Enums (`NodeKind = MODULE|CLASS|FUNCTION|METHOD|WHY_COMMENT`, `EdgeKind = DEFINES|CALLS|IMPORTS|INHERITS|DOCUMENTS`, `Confidence = HIGH|MEDIUM|LOW`) inherit from `str, Enum` so `sqlite3 graph.db .dump` stays human-readable.

`create_engine(db_path)` returns an `AsyncEngine` with `SQLModel.metadata.create_all` applied idempotently inside a single `engine.begin()` transaction. URL scheme decides the driver: `sqlite+libsql://...` for local file or hosted Turso, `sqlite+aiosqlite://...` as a fallback when the libsql wheel is unavailable. There is no Alembic at v1 — re-index by deleting `.pyarnes/graph.db` until the first breaking schema change.

The repository helpers (`upsert_nodes`, `upsert_edges`, `upsert_index_meta`, `neighbors`, `get_node`) use `session.merge(...)` for upsert. Storage failures map to the standard taxonomy: lock contention raises `TransientError` (retried with exponential backoff), missing libsql raises `UserFixableError`, corrupt DB raises `UnexpectedError`.

## Extraction and indexing

Two builders implement the abstract `CodeGraphBuilder` (`async def build(path) -> tuple[list[GraphNode], list[GraphEdge]]`):

- **`TreeSitterBuilder`** — Python via `tree-sitter-python`. Two-pass extraction per file: pass 1 emits `DEFINES` edges for every symbol; pass 2 resolves call targets against the pass-1 symbol table. Unresolved targets land as `Confidence.LOW` edges so the model can still use them.
- **`WhyCommentBuilder`** — case-insensitive regex scan for `^\s*#\s*(WHY|HACK|NOTE|TODO)\b:?`. Each hit becomes a `WHY_COMMENT` node with a `DOCUMENTS` edge to the enclosing function/class/module (found by walking the Tree-sitter AST upward). Captures rationale that lives inline rather than in a separate doc.

`Indexer` walks a root path, computes SHA-256 of raw bytes per file, compares against `IndexMeta`, and re-parses only on mismatch. The parser version is part of `IndexMeta` so a Tree-sitter grammar upgrade busts the cache cleanly. Each parse event is recorded through the existing `ToolCallLogger` JSONL stream with `tool="graph.index"` — so PR-05's `graph:usage` reads from the same log without writer duplication.

Two task-runner entries:

- `graph:index <path>` — full incremental index of `<path>`.
- `graph:watch <path>` — `watchfiles.awatch`-driven incremental re-index on change events, filtered by path predicate (`src/`, `tests/`, `packages/*/src/`) so editor lockfile churn doesn't re-trigger.

## Analytics and reporting

`graph_view.build_nx(session, kinds, min_confidence)` materialises the relevant subgraph as an `nx.DiGraph` once per analysis run; the three analyses share it. `min_confidence` lets planning tasks exclude `Confidence.LOW` edges while exploration tasks include them.

- **Blast radius** — `blast_radius(session, node_id, direction)` returns the affected-symbol set via NetworkX `descendants`/`ancestors` over the `CALLS` ∪ `IMPORTS` subgraph.
- **Centrality** — betweenness + in-degree rankings; "god nodes" flagged by composite score `0.7 * in_degree_norm + 0.3 * betweenness_norm`, top `ceil(len(nodes) * 0.01)`. On graphs > 10k nodes, `nx.betweenness_centrality` is subsampled (`k=100`).
- **Communities** — Leiden via `graspologic.partition.leiden` on the undirected symmetrisation of the call graph. `graspologic` is an optional extra (`pyarnes-graph[communities]`); when the import fails the report degrades gracefully with "(communities disabled)".

`report.compose(session)` renders `templates/graph_report.md.j2` (sections: Overview, God Nodes, Communities, Hot Paths, Design Intent) with a hard ~2000-token cap (estimated as `len(text) / 4`). Sections truncate bottom-up when over budget — Hot Paths shrinks first; Design Intent (the `# WHY` payload) is preserved last because it is the irreplaceable signal. The template lives in `templates/` so adopters can fork it without touching code, and the golden-file test asserts stable output across runs.

`graph:report` writes the rendered report to `.pyarnes/GRAPH_REPORT.md`.

## Tools and MCP server

Four `ToolHandler` subclasses cover every planned skill. Each is wrapped by the same `GuardrailChain` callers use elsewhere — `ToolAllowlistGuardrail` (only these four) plus `PathGuardrail` (restrict to `.pyarnes/` and indexed roots).

| Tool | Purpose |
|---|---|
| `GetNodeTool` | Look up a single node by id; falls back to fuzzy name match returning top-3 candidates, raises `LLMRecoverableError` for zero matches so the model can refine. |
| `GetNeighborsTool` | Neighbors filtered by `EdgeKind`. |
| `ShortestPathTool` | NetworkX shortest path between two node ids. |
| `BlastRadiusTool` | Wraps `analysis.blast_radius` for direct LLM use. |

`build_graph_registry(engine) -> ToolRegistry` is the single factory: `AgentLoop`, the MCP server, and adopter code share one registry definition.

`mcp/server.py` is a thin stdio JSON-RPC server using the official `mcp` SDK. Each `Server.list_tools` / `Server.call_tool` decorator delegates straight to the same `ToolHandler` instances — one code path, two transports. JSON-RPC frames go to stdout; logs go to stderr via the standard logging config (matching the project's stdout/stderr discipline). Invocation: `python -m pyarnes_graph.mcp.server`.

`hooks/pretooluse.py` is a PreToolUse hook entrypoint. It detects `Read` / `Glob` / `Grep` tool calls and prepends `GRAPH_REPORT.md` contents to the agent context exactly once per session (idempotency tracked via `.pyarnes/session/<session-id>/report-injected.flag`). On stale reports (mtime older than the newest `IndexMeta` row), it warns to stderr and injects anyway. **The stdin/stdout JSON contract, exit-code semantics, and `settings.json` registration shape are owned by `06-hook-integration.md` — do not duplicate here.** `pyarnes_graph.hooks.pretooluse` is the entrypoint name a host's `settings.json` references.

## Evaluation

Two scorers conforming to the canonical `Scorer.score(...) -> ScoreResult` contract from `07-bench-integrated-axes.md` (note: PR-05 predated that contract and described scorers as returning `float` — the spec-07 signature is authoritative):

- **`TokenReductionScorer`** — pure local computation, no `usage`. `baseline_tokens` = naive "read all relevant files" tiktoken sum; `graph_tokens` = `GRAPH_REPORT.md` + N graph-tool-call response sums. `score = clip((baseline - graph) / baseline, 0, 1)`. A 5× reduction maps to `score = 0.8`.
- **`LLMJudgeScorer`** — takes a `ModelClient` in its constructor (the caller injects Claude / OpenAI / a stub at the edge so CI stays offline-capable). Asks the judge: "does `actual` contain enough information to answer the task in `expected`?". Returns a `ScoreResult` whose `usage` records the judge call's tokens, so `EvalSuite.run()` can include evaluation cost in the total — see `07-bench-integrated-axes.md` for the integration mechanics.

The `EvalSuite("graph-token-reduction")` runs scenarios across three fixture repos (small ~20 files, medium ~200, react-like ~1000) shipped as tarballs unpacked at test time. **`EvalSuite.run()` itself, the `summary()` shape, and the `EvalResult` schema are owned by `07-bench-integrated-axes.md` and `13-run-logger.md` — do not redefine here.**

`graph:usage` is a pure reader of the JSONL capture log written by the indexer and the MCP server. It produces a markdown histogram (`tool_name`, `call_count`, `total_duration_seconds`, `p50_ms`, `p99_ms`) at `.pyarnes/USAGE.md`.

`graph:ci` is a composite task: `graph:index` → `graph:eval`, fails when median reduction across fixtures < 0.8 (5×) or when the smallest fixture falls below 0.5 (2×) — the second floor prevents pass-by-averaging.

## Skills and template integration

Four skills consume the tools and report. They live under `template/.claude/skills/<name>/SKILL.md` following the YAML-frontmatter + section-header convention established by `python-test/SKILL.md`:

| Skill | What it drives |
|---|---|
| `/overview` | Read-only: emits a high-level architecture briefing from `graph:report` + `GetNodeTool`. Never writes files. |
| `/impact` | `GetNodeTool` (with fuzzy match) → `BlastRadiusTool` in both directions. Inputs: a symbol name or file path. |
| `/patch` | `ShortestPathTool` + `GetNeighborsTool` to localise an edit and surface the nearby code the model should read. Plans the location; does not write. |
| `/ship` | Runs `graph:ci` and renders pass/fail with the reduction ratio. On failure, emits a structured report and asks the user whether to proceed (loud, not blocking). |

The PreToolUse hook is wired into `template/.claude/settings.json` additively (existing hooks preserved), pointing at `pyarnes_graph.hooks.pretooluse`. `scripts/smoke-template.sh` asserts each `SKILL.md` exists in a freshly-generated project and that the hook registration is present in `settings.json`.

## Cross-references

- `02-message-bus.md` — the MVCC rationale for choosing libsql over stdlib SQLite is the same one used here for concurrent indexer writes.
- `06-hook-integration.md` — owns the hook contract (stdin JSON, exit codes, `settings.json` shape). This spec only names the entrypoint.
- `07-bench-integrated-axes.md` — owns `Scorer` / `ScoreResult` / `EvalResult` / `EvalSuite.run()`. The two graph scorers conform to that contract.
- `13-run-logger.md` — owns `EvalResult` extension fields and run-level persistence; `graph:eval` emits rows that conform.
- `15-tooling-artifacts.md` — `.pyarnes/graph.db`, `.pyarnes/GRAPH_REPORT.md`, `.pyarnes/USAGE.md`, `.pyarnes/eval/*.jsonl`, and `.pyarnes/session/<id>/` are all transient developer artifacts under that spec's policy.
