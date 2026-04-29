# pyarnes_bench.audit — Code-Audit Subpackage (Two-Phase Plan)

> **Spec header**
>
> | Field | Value |
> |---|---|
> | **Title** | pyarnes_bench.audit — Code-Audit Subpackage (Two-Phase Plan) |
> | **Status** | active |
> | **Type** | optional-subsystem |
> | **Tags** | audit, code-graph, navigation, dead-code, complexity |
> | **Owns** | `pyarnes_bench.audit` subpackage layout, Python-only tree-sitter parser, networkx graph schema, JSON-on-disk persistence, eight detectors (unused files / exports / deps, circular imports, duplicate blocks, complexity hotspots, boundary violations, feature-flag usage), structural analyses (god nodes, surprises, suggested questions), audit event emitters, four `tasks audit:*` CLI entries, and the deferred Phase-2 enhancement contract |
> | **Depends on** | 10-hook-integration.md, 15-bench-integrated-axes.md, 16-run-logger.md |
> | **Extends** | — |
> | **Supersedes** | PR-01-graph-package-foundation.md, PR-02-extractor-and-indexer.md, PR-03-analytics-and-report.md, PR-04-tools-mcp-and-hook.md, PR-05-eval-and-usage-tracking.md, PR-06-skills-template-docs.md |
> | **Read after** | 16-run-logger.md |
> | **Read before** | — |
> | **Not owned here** | runtime loop (`07-swarm-api.md`); evaluation contracts (`15-bench-integrated-axes.md`); message-safety pipeline (`11-message-safety.md`); external hook event-JSON contract (`10-hook-integration.md`); shared `estimate_tokens` helper (`pyarnes_core.observability.tokens`) |
> | **Last reviewed** | 2026-04-29 |

## Why

The original spec proposed a separate `pyarnes_graph` workspace member backed by libsql + Leiden + Jinja2 + an MCP server. Both predecessor tools that motivated it — `graphifyy` (CLI: `graphify`) and `code-review-graph` — are being removed: the first needs an LLM on first run and pulls `graspologic` (numpy/scipy/numba/numba-llvmlite); the second is an external MCP server that adopters do not want. We replace both with an in-tree, LLM-free, Python-only subpackage that lives **inside** `pyarnes_bench`, not in a new workspace member.

The replacement ships in two phases.

- **Phase 1** — `pyarnes_bench.audit`: tree-sitter-python parser → `networkx` graph → JSON on disk → cheap structural analyses + eight detectors + four CLI entries. No LLM, no MCP server, no extra workspace member.
- **Phase 2** — opt-in additive enhancements to the same subpackage, gated behind extras (`pyarnes-bench[audit-mvcc]`, `pyarnes-bench[audit-leiden]`) and not implemented until needed.

## Scope by phase

### Phase 1 (v1, ships now)

```
packages/bench/src/pyarnes_bench/audit/
├── __init__.py          # public re-exports
├── schema.py            # NodeKind, EdgeKind enums; Node, Edge dataclasses
├── events.py            # log_audit_indexed / log_audit_analyzed / log_audit_finding
├── parser.py            # PythonParser (tree-sitter-python) → list[Node], list[Edge]
├── builder.py           # build_graph(root, *, session_id, trace_id) -> nx.DiGraph
├── store.py             # save_graph / load_graph via networkx node_link + write_private
├── analyze.py           # god_nodes, surprising_connections, suggested_questions
├── audit.py             # audit_graph: orchestrate the eight detectors
├── boundaries.py        # check_boundaries(g, rules) -> list[Finding]
├── duplicates.py        # detect_duplicates(g, *, min_tokens) -> list[Finding]
├── config.py            # AuditConfig.load(project_root) — reads [tool.pyarnes-audit]
├── findings.py          # Finding dataclass + summarize()
└── README.md            # 1-page overview
```

Public surface re-exported from `pyarnes_bench/__init__.py` so external callers can write `from pyarnes_bench import build_graph, audit_graph`.

### Phase 2 (future, opt-in extras inside `pyarnes_bench`)

Documented but not implemented:

- `pyarnes-bench[audit-mvcc]` — swap JSON persistence for libsql via `sqlalchemy-libsql`. Gated by `[tool.pyarnes-audit].persistence = "libsql"`. Same `save_graph` / `load_graph` API.
- `pyarnes-bench[audit-leiden]` — replace `networkx.community.greedy_modularity_communities` with Leiden via `graspologic.partition.leiden`. Gated by `[tool.pyarnes-audit].community = "leiden"`; falls back to greedy modularity if the extra is absent.
- `pyarnes_bench.audit.report` — Jinja2 markdown report (`GRAPH_REPORT.md`, ≤2k tokens). Template forkable from `pyarnes_bench/audit/templates/`.
- `pyarnes_bench.audit.mcp` — stdio MCP server (`python -m pyarnes_bench.audit.mcp`) wrapping the same Phase-1 functions; only registered if the adopter opts in.
- `pyarnes_bench.audit.viz` — single-file `graph.html` (vis-network from CDN, embedded JSON).

Phase 2 changes never break Phase 1 callers; every new feature is additive behind an extra or a config flag.

## Schema

```python
class NodeKind(StrEnum):
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    FILE = "file"

class EdgeKind(StrEnum):
    CONTAINS = "contains"
    IMPORTS = "imports"
    IMPORTS_FROM = "imports_from"
    CALLS = "calls"
    INHERITS = "inherits"

@dataclass(frozen=True, slots=True)
class Node:
    id: str                # f"{relative_path}::{qualname}" — deterministic, stable
    kind: NodeKind
    name: str
    file_path: str
    line_start: int
    line_end: int
    qualname: str
    extra: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class Edge:
    src: str
    dst: str
    kind: EdgeKind
    file_path: str
    line: int = 0
    extra: dict[str, Any] = field(default_factory=dict)
```

`StrEnum` keeps the on-disk JSON human-readable. Phase 2 adds no new enum values.

## Parser

`PythonParser.parse_file(path: Path) -> tuple[list[Node], list[Edge]]`. Single language, tree-sitter-python. Pattern lifted from `tirth8205/code-review-graph/parser.py` but with the polyglot dispatch removed: one extension, one grammar, one recursive `_extract_from_tree`. Extracts `class_definition`, `function_definition`, `import_statement`, `import_from_statement`, and `call`; emits `CONTAINS`, `IMPORTS`, `IMPORTS_FROM`, `CALLS`, `INHERITS` edges with line numbers.

Phase 2 may add other languages by reusing the same `parse_file` shape.

## Persistence

Phase 1: `<project_root>/.pyarnes/audit/graph.json` via `networkx.node_link_data(graph, edges="edges")` written through `pyarnes_core.atomic_write.write_private`. The `.pyarnes/` directory is in the project's `.gitignore` and ruff exclude list.

Phase 2: `[tool.pyarnes-audit].persistence = "libsql"` switches to a sqlite/libsql file at the same path; the `[tool.pyarnes-audit].community = "leiden"` flag switches the analysis. Both are no-ops without the matching extra installed (`pyarnes-bench[audit-mvcc]`, `pyarnes-bench[audit-leiden]`).

## Configuration

Source-controlled in `pyproject.toml` under `[tool.pyarnes-audit]`. Read by `AuditConfig.load(project_root)` using the same pattern as `_load_config()` in `pyarnes_tasks/cli.py`.

```toml
[tool.pyarnes-audit]
graph_path = ".pyarnes/audit/graph.json"
roots = ["packages/core/src", "packages/harness/src", "packages/bench/src"]
exclude = [".venv", ".pyarnes", "__pycache__", "node_modules", ".git"]
forbidden_edges = [
  ["pyarnes_core", "pyarnes_harness"],
  ["pyarnes_core", "pyarnes_bench"],
]
flag_pattern = "feature_flag\\(['\"](\\w+)['\"]\\)"
duplicate_min_tokens = 40

# Phase 2 (no-op without the matching extra installed)
persistence = "json"            # or "libsql"
community   = "modularity"      # or "leiden"
```

Any missing key falls back to a default so `audit:check` still runs in a project that omits the table entirely.

## Analyses

`analyze.py` exposes three functions; each returns plain dicts/lists serialisable to JSON.

- `god_nodes(g, *, top_n=10)` — top-N nodes by combined in-degree + out-degree, excluding `FILE` nodes.
- `surprising_connections(g, *, top_n=10)` — cross-community edges. Communities via `networkx.community.greedy_modularity_communities` (stdlib, no `graspologic`).
- `suggested_questions(g, *, top_n=7)` — questions derived from bridge nodes (high `betweenness_centrality`, sampled at `k=500` for graphs > 5000 nodes), god nodes, isolated subgraphs, and untested hotspots (>5 callers, no `tests/test_*` caller).

Reference implementations: `safishamsi/graphify/analyze.py` and `tirth8205/code-review-graph/analysis.py`. Phase-1 code uses **only** networkx stdlib.

## Audits

`audit.py::audit_graph(g, cfg) -> list[Finding]` orchestrates eight detectors. Each detector is short (≤30 lines) and emits findings via `log_audit_finding`.

| Detector | Implementation |
|---|---|
| `unused_files` | `MODULE` nodes with zero incoming `IMPORTS`/`IMPORTS_FROM`. |
| `unused_exports` | Public symbols (no leading underscore) with zero incoming `CALLS`/`IMPORTS_FROM`. Cross-checked against `vulture --min-confidence 80` to drop dynamic-dispatch false positives. |
| `unused_dependencies` | `[project].dependencies` from each package's `pyproject.toml` vs top-level imports observed in the graph. |
| `circular_imports` | `networkx.simple_cycles` on the imports-only subgraph. |
| `duplicate_blocks` | `duplicates.detect_duplicates`: hash normalised function bodies (`ast.unparse(ast.parse(...))`, docstrings stripped); group by hash; report pairs above `duplicate_min_tokens` (≈40). |
| `complexity_hotspots` | `radon cc <root> --min B --json` (subprocess); ingest functions with rank ≥ C; attach to the matching node. |
| `boundary_violations` | Walk imports; flag any edge crossing `forbidden_edges`. |
| `feature_flag_usage` | `flag_pattern` regex over source files; one finding per flag with hit count, so the user can ramp down on retired flags. |

Severity is `HIGH | MEDIUM | LOW`; `audit:check` exits non-zero when any HIGH finding is present.

## Observability

`pyarnes_bench.audit.events` defines three typed emitters that mirror the shape of the core typed emitters (`log_lifecycle_transition`, `log_tool_call`, `log_guardrail_violation`) — mandatory `session_id` / `trace_id` / `step` keyword-only context, calling `log_event` from `pyarnes_core.observability`:

- `log_audit_indexed(logger, root, *, files, nodes, edges, duration_ms, session_id, trace_id, step)` → event `"audit.indexed"`.
- `log_audit_analyzed(logger, kind, *, count, session_id, trace_id, step)` → event `"audit.analyzed"`. `kind ∈ {god_nodes, surprises, questions}`.
- `log_audit_finding(logger, category, target, severity, *, session_id, trace_id, step, detail)` → event `"audit.finding"`.

Living next to the audit code keeps core free of bench-feature coupling and lets the whole subpackage migrate cleanly when it is later moved to the common swarm.

## CLI

`packages/tasks/src/pyarnes_tasks/cli.py` registers four entries; each task module is a thin shim that generates `session_id` / `trace_id`, dispatches to the audit subpackage, prints a token-bounded human summary to stdout, and lets structured events stream to stderr via the existing logger.

| Task | Purpose |
|---|---|
| `audit:build` | `build_graph(root, …)` → `save_graph(g, graph_path)`. |
| `audit:show` | `load_graph(graph_path)` → human summary (kinds counts, top files, top nodes, total `estimate_tokens` of the node-link payload). |
| `audit:analyze` | `god_nodes`, `surprising_connections`, `suggested_questions`. |
| `audit:check` | `audit_graph(...)`; non-zero exit on HIGH findings; suitable for CI. |

Phase 2 adds `audit:report` (Jinja2 render) and `audit:mcp` (stdio MCP server) only when the matching extras are installed.

## Reuse map

The subpackage stays small by reusing existing primitives.

| Used | From |
|---|---|
| `log_event`, `iso_now`, `start_timer`, `monotonic_duration`, `to_jsonable`, `dumps`, `LoggerPort` | `pyarnes_core.observability` |
| `get_logger(__name__)` | `pyarnes_core.observe.logger` |
| `write_private`, `append_private` | `pyarnes_core.atomic_write` |
| `TransientError`, `LLMRecoverableError`, `UserFixableError`, `UnexpectedError` | `pyarnes_core.errors` |
| `estimate_tokens` (newly extracted) | `pyarnes_core.observability.tokens` |
| `version_of("pyarnes-bench")` | `pyarnes_core.packaging` |
| `[tool.pyarnes-audit]` config-loader pattern | mirror `_load_config()` in `pyarnes_tasks/cli.py` |
| `more_itertools.batched`, `funcy.distinct`, `toolz.pipe` | already deps |
| `vulture`, `radon` (subprocessed) | already deps in `dev` group |

## Migration into the swarm

The "later moved to the common swarm" plan is a directory rename: lift `packages/bench/src/pyarnes_bench/audit/` into the swarm package, update one `__init__.py` re-export, and adjust the four CLI entries. Both phases move together; the contract here is the boundary that guarantees that's a one-day change rather than a refactor.

## Cross-references

- `10-hook-integration.md` — owns the hook contract; Phase 2's MCP server uses the same stdin-JSON / exit-code shape.
- `15-bench-integrated-axes.md` — owns `Scorer` / `ScoreResult`. Phase 2 may add audit-derived scorers; Phase 1 does not.
- `16-run-logger.md` — owns `EvalResult` extension fields; audit events use `log_event` and do not duplicate that surface.
- `17-tooling-artifacts.md` — `.pyarnes/audit/graph.json` is a transient developer artifact under that spec's policy.
