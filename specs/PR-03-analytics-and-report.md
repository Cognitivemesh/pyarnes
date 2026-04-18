# PR-03 — Graph Analytics and `GRAPH_REPORT.md`

## Context

PR-02 gives us a populated `GraphNode` / `GraphEdge` store. This PR turns it
into something humans and agents can reason about: blast-radius queries,
centrality rankings ("god nodes"), community detection for architectural
clusters, and a compact Markdown report (`GRAPH_REPORT.md`) that fits in one
model context window. The report is the artifact the PreToolUse hook (PR-04)
injects into Claude Code sessions to replace bulk file reads — it's the
mechanism that delivers the 5×-71× token-reduction target.

## Scope

**In**

- `analysis/blast_radius.py` — `async def blast_radius(session, node_id,
  direction)` returning affected-symbol set via NetworkX
  `descendants`/`ancestors` on the subgraph of `CALLS` + `IMPORTS` edges.
- `analysis/centrality.py` — betweenness + in-degree rankings; flags "god
  nodes" (top 1% by in-degree + centrality composite score).
- `analysis/communities.py` — Leiden clustering via `graspologic` on the
  undirected symmetrization of the call graph.
- `analysis/report.py` — composes `GRAPH_REPORT.md` from the above, capped at
  ~2k tokens.
- `graph:report` task — writes `.pyarnes/GRAPH_REPORT.md`.
- Unit tests + a golden-file test for the report template.

**Out**

- Tool wrappers exposing these queries as `ToolHandler` subclasses — PR-04.
- MCP server exposing them over JSON-RPC — PR-04.
- Token-reduction measurement vs baseline — PR-05.

## Files

### New

- `packages/graph/src/pyarnes_graph/analysis/__init__.py`
- `packages/graph/src/pyarnes_graph/analysis/graph_view.py` — helper:
  `async def build_nx(session, kinds) -> nx.DiGraph` that materializes the
  subgraph once so the three analyses share it.
- `packages/graph/src/pyarnes_graph/analysis/blast_radius.py`
- `packages/graph/src/pyarnes_graph/analysis/centrality.py`
- `packages/graph/src/pyarnes_graph/analysis/communities.py`
- `packages/graph/src/pyarnes_graph/analysis/report.py`
- `packages/graph/src/pyarnes_graph/templates/graph_report.md.j2` — Jinja2
  template for the report (sections: Overview / God Nodes / Communities /
  Hot Paths / Design Intent).
- `tests/unit/graph/test_blast_radius.py` — property test: `ancestors` of a
  leaf is a subset of `ancestors` of any of its callers.
- `tests/unit/graph/test_centrality.py` — seeded random graph, assert
  stable top-3 ordering.
- `tests/unit/graph/test_communities.py` — planted-partition graph, assert
  recovered communities match ground truth with ARI ≥ 0.9.
- `tests/unit/graph/test_report.py` — golden-file test against a fixture
  database produced by running the indexer over `fixtures/canonical.py`.

### Modified

- `packages/graph/pyproject.toml` — add `graspologic>=3.4`, `jinja2>=3.1`.
  `networkx` was pulled in by PR-02.

## Reuse

| Existing utility | File | Used for |
|---|---|---|
| `get_logger` | core | Structured logs for each analysis step. |
| `EvalSuite` / `EvalResult` | `packages/bench/.../eval.py` | **Not** used for report generation — they're for PR-05's scoring. Kept out of scope here. |
| Repository helpers | PR-01 | `analysis/graph_view.py` selects nodes + edges via the existing repo API; no raw SQL. |
| `watchfiles` | root dev group | `graph:report` can optionally re-run on DB change (nice-to-have, not required for this PR). |
| Radon / Vulture / Bandit findings | root dev group | Attach CC / dead-code / security findings as `extra` JSON on nodes during reporting — the ingestion itself lives in PR-05, this PR just renders them if present. |

## Design notes

1. **Materialize the NX graph once per `graph:report` run.** The three
   analyses share an `nx.DiGraph`; rebuilding it three times would cost ~3× I/O.
2. **Confidence filter in NX view.** `graph_view.build_nx` accepts a
   `min_confidence` kwarg so "planning" tasks can exclude `Confidence.LOW`
   edges (unresolved call targets) while "exploration" tasks include them.
3. **Report token budget.** Hard cap of ~2000 tokens (estimated via
   `len(text) / 4`). If sections overflow, truncate bottom-up (Hot Paths
   shrinks first, Design Intent is preserved). This is the knob we'll tune
   against PR-05's `TokenReductionScorer`.
4. **God-node heuristic**: composite score `= 0.7 * in_degree_norm + 0.3 *
   betweenness_norm`. Top ceiling(len(nodes) * 0.01) nodes flagged. Threshold
   is tunable via `graph_report.md.j2` front-matter — no code change to adjust.
5. **Leiden over Louvain**: `graspologic.partition.leiden` is the default in
   their API and is strictly better at small-community recovery — matches the
   parent plan's reference to graph-based clustering for architectural views.
6. **Jinja2 template, not string interpolation.** Makes the report's
   structure legible and user-editable (adopters can fork the template). Also
   enables the golden-file test to assert stable output across runs.

## Acceptance

```bash
uv run tasks graph:index .      # from PR-02
uv run tasks graph:report       # this PR
cat .pyarnes/GRAPH_REPORT.md    # < 2000 tokens by wc estimate
```

Report sections (golden-file asserted):

1. `## Overview` — N modules, N classes, N functions, parser version.
2. `## God Nodes` — table of top-K nodes by composite score.
3. `## Communities` — bullet list per community with member count + seed members.
4. `## Hot Paths` — top-5 longest `CALLS`-edge chains (by shortest path between
   community centroids).
5. `## Design Intent` — all `WHY_COMMENT` nodes grouped by enclosing module.

Unit checks:

- `test_blast_radius.py` — property test on 100 random DAGs.
- `test_centrality.py` — seeded reproducibility.
- `test_communities.py` — planted-partition recovery.
- `test_report.py` — golden-file diff on the canonical fixture DB.

## Risks & rollback

- **Risk**: `graspologic` has a heavy scientific-Python dep tree (numpy /
  scipy / numba). **Mitigation**: mark it as an optional extra
  (`pyarnes-graph[communities]`) so CI and slim adopters can skip it. The
  report template falls back to "(communities disabled)" when the import
  fails.
- **Risk**: `nx.betweenness_centrality` is O(V·E) and slow on large graphs.
  **Mitigation**: subsample via `nx.betweenness_centrality(..., k=100)` when
  `len(graph) > 10_000`. Configurable via env var.
- **Rollback**: revert; PR-01 and PR-02 remain fully functional. The report
  artifact is a pure output, no consumer depends on it yet.

## Exit criteria

- [ ] `graph:report` produces a report ≤ 2000 tokens on a 10k-node graph.
- [ ] All unit tests green; golden-file test stable across 10 repeated runs.
- [ ] `uv run tasks check` green.
- [ ] `graspologic` import failure degrades gracefully (report still produced
  without the Communities section).
