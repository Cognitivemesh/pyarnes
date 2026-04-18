# PR-02 — Tree-Sitter Extractor and Incremental Indexer

## Context

Builds on PR-01's empty schema by **populating** it from a real codebase.
Introduces the tree-sitter based AST extractor, the `# WHY` / `# HACK`
design-intent comment scanner, and the SHA-256-keyed incremental indexer that
re-parses only files whose content has changed. After this PR, a user can run
`uv run tasks graph:index` on any Python repo and get a filled `GraphNode` /
`GraphEdge` database plus an `IndexMeta` row per file.

Indexing is the foundation of every downstream feature — analytics (PR-03),
tools (PR-04), and evals (PR-05) all read from the DB this PR writes to.

## Scope

**In**

- `builder/tree_sitter.py` — Python-only extractor using
  `tree-sitter-python`. Emits `NodeKind.{MODULE,CLASS,FUNCTION,METHOD}` and
  `EdgeKind.{DEFINES,CALLS,IMPORTS,INHERITS}`.
- `builder/why_comments.py` — regex scanner for `# WHY:`, `# HACK:`,
  `# NOTE:`, `# TODO:` lines → `NodeKind.WHY_COMMENT` nodes with
  `EdgeKind.DOCUMENTS` edges pointing at the enclosing symbol.
- `indexer.py` — async walker: for each source file, compute SHA-256,
  compare against `IndexMeta`, parse+upsert on mismatch, update meta.
- `graph:index <path>` and `graph:watch <path>` tasks (auto-discovered).
- Unit tests on canonical fixture files + a property test: every parsed
  function has exactly one `DEFINES` edge from its enclosing module/class.

**Out**

- Multimodal ingestion (`.md`, `.pdf`) — deferred, listed in plan's "Out of
  scope".
- JS/TS/Rust/Go extractors — plan explicitly defers these.
- Watchmode file-level debouncing — `watchfiles` default 50ms is fine.
- Analytics (`blast_radius`, etc.) — PR-03.

## Files

### New

- `packages/graph/src/pyarnes_graph/types.py` — `CodeGraphBuilder(ABC)` with a
  single async `build(path: Path) -> tuple[list[GraphNode], list[GraphEdge]]`
  method. Subclassed by `TreeSitterBuilder` and `WhyCommentBuilder`.
- `packages/graph/src/pyarnes_graph/builder/__init__.py`
- `packages/graph/src/pyarnes_graph/builder/tree_sitter.py` — `TreeSitterBuilder(CodeGraphBuilder)`.
- `packages/graph/src/pyarnes_graph/builder/why_comments.py` — `WhyCommentBuilder(CodeGraphBuilder)`.
- `packages/graph/src/pyarnes_graph/indexer.py` — `Indexer` class with
  `async def index(root: Path)` and `async def watch(root: Path)`.
- `packages/graph/src/pyarnes_graph/tasks.py` — registers `graph:index`,
  `graph:watch` commands consumable by `uv run tasks`.
- `tests/unit/graph/fixtures/canonical.py` — a ~60-line Python file with a
  class, two methods, one function, two `# WHY:` comments, and one import.
- `tests/unit/graph/test_tree_sitter_builder.py` — asserts node/edge counts
  and kinds for `canonical.py`.
- `tests/unit/graph/test_why_comments.py` — asserts the two WHY nodes exist
  with correct `DOCUMENTS` edges.
- `tests/unit/graph/test_indexer.py` — asserts SHA-256 skip: index twice,
  second pass produces zero parse events.
- `tests/features/graph.feature` — Gherkin scenarios for
  `graph:index` and `graph:watch`.
- `tests/features/steps/graph_steps.py` — pytest-bdd step defs.

### Modified

- `packages/graph/pyproject.toml` — add `tree-sitter>=0.23`,
  `tree-sitter-python>=0.23`, `networkx>=3.3` (PR-03 needs it, introducing now
  avoids a second dep bump).
- `packages/graph/src/pyarnes_graph/__init__.py` — export `Indexer`,
  `TreeSitterBuilder`, `WhyCommentBuilder`.

## Reuse

| Existing utility | File | Used for |
|---|---|---|
| `ToolCallLogger` + `ToolCallEntry` | `packages/harness/src/pyarnes_harness/capture/tool_log.py` | Each file-parse is logged as one JSONL entry with `tool="graph.index"`. Same file is later read by `graph:usage` (PR-05). |
| `ToolCallLogger.start_timer()/stop_timer()` | same file | Per-file stopwatch. No `time.monotonic` duplication. |
| `CapturedOutput` + `OutputCapture` | `packages/harness/src/pyarnes_harness/capture/output.py` | Tree-sitter parse errors are recorded via `record_failure`; success paths via `record_success`. Matches the existing tool-capture pattern. |
| `TransientError` / `LLMRecoverableError` | `packages/core/src/pyarnes_core/errors.py` | Partial-file-read during indexing (file being edited mid-walk) raises `TransientError` with `max_retries=2`. Unknown-file-type raises `LLMRecoverableError`. |
| `Lifecycle` FSM | `packages/core/src/pyarnes_core/lifecycle.py` | `Indexer` owns a `Lifecycle` wrapper mapping indexer phases (IDLE, INDEXING, READY, UPDATING, FAILED) onto the existing `Phase` enum. No changes to core. |
| `watchfiles>=1.0` | root `pyproject.toml` dev group | Powers `graph:watch` without any new dep. |
| Repository helpers from PR-01 | `packages/graph/src/pyarnes_graph/store/repository.py` | `upsert_nodes`, `upsert_edges`, + a new helper `upsert_index_meta`. |

## Design notes

1. **Stable node ids**: `"{relative_path}::{qualname}"`. Deterministic,
   survives file renames only via `UPDATE IndexMeta` (rename = delete + add,
   acceptable for v1).
2. **Two-pass extraction per file**: pass 1 emits `DEFINES` edges for every
   symbol; pass 2 resolves call-site targets against the pass-1 symbol table.
   Call targets that don't resolve become edges with
   `Confidence.LOW` — the agent can still use them.
3. **SHA-256 of raw bytes**, not normalized content. Simpler, faster, and the
   cost of occasional whitespace-only re-index is negligible at scale.
4. **Parser version in `IndexMeta`**: busts cache when tree-sitter-python
   version changes — no stale AST nodes surviving upgrades.
5. **`Indexer.watch` uses `watchfiles.awatch`** — already async, no threadpool
   shim. Each change event triggers a single-file re-index, not a full walk.
6. **`# WHY:` pattern**: case-insensitive match on `r"^\s*#\s*(WHY|HACK|NOTE|TODO)\b:?"`.
   The enclosing symbol is found by walking the tree-sitter AST upward to the
   nearest `function_definition` / `class_definition`; module-level comments
   attach to the `MODULE` node.

## Acceptance

```bash
# Run from the repo root against pyarnes itself (good dogfood)
uv run tasks graph:index .
# Expect: .pyarnes/graph.db exists, >1000 nodes, >1000 edges

uv run tasks graph:index .      # second pass
# Expect: JSONL capture log shows zero parse events (all SHA-256 hits)

uv run tasks graph:watch . &    # watch mode in background
echo "# WHY: smoke" >> packages/graph/src/pyarnes_graph/indexer.py
# Expect: within 2s, one parse event for indexer.py
```

Unit checks:

- `test_tree_sitter_builder.py`: parse `canonical.py`, assert exact counts
  (1 MODULE, 1 CLASS, 3 FUNCTION/METHOD, N IMPORTS, N CALLS edges).
- `test_why_comments.py`: parse `canonical.py`, assert 2 `WHY_COMMENT` nodes
  + 2 `DOCUMENTS` edges.
- `test_indexer.py`: property test — for any sequence of (create / edit /
  no-op) file operations, `len(capture_log_entries) == len(changed_files)`.
- BDD `graph.feature` covers the three scenarios from the plan's verification
  section (index completes in <10s on a 1k-file repo, re-index is a no-op,
  blast-radius query can resolve a known function — the last scenario uses a
  placeholder that PR-03 makes real).

## Risks & rollback

- **Risk**: tree-sitter grammar wheel missing for a Linux arch in CI.
  **Mitigation**: fall back to `tree_sitter_languages` (bundled grammars) if
  the standalone wheel fails to build. Document in the spec's "follow-ups".
- **Risk**: watchfiles fires rapidly during `uv sync` rewriting lockfiles.
  **Mitigation**: filter events by path predicate (`src/`, `tests/`,
  `packages/*/src/`) before enqueueing.
- **Rollback**: revert the PR; PR-01's empty schema remains usable. The
  `.pyarnes/graph.db` file written by this PR is disposable (re-generatable).

## Exit criteria (all must hold)

- [ ] `uv run tasks graph:index <some-repo>` populates the DB.
- [ ] Re-running the same command triggers zero parses.
- [ ] `uv run tasks check` green.
- [ ] Indexing 1k files completes in <10s on a dev laptop.
- [ ] BDD `graph.feature` scenarios pass.
- [ ] Coverage for the new modules ≥ 50%.
