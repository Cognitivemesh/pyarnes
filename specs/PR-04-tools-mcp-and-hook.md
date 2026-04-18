# PR-04 — Graph Tools, MCP Server, and PreToolUse Hook

## Context

PR-03 produced a queryable analytics layer plus a compact `GRAPH_REPORT.md`.
This PR exposes that capability **to the LLM** via three integration surfaces:
(a) four `ToolHandler` subclasses usable from the existing `AgentLoop`, (b) a
stdio MCP server that external hosts (Claude Desktop, Claude Code) can connect
to, and (c) a PreToolUse hook that injects `GRAPH_REPORT.md` into the session
context before the first `Read`/`Glob` tool call — this is the mechanism that
operationalizes the 5×-71× token-reduction target.

After this PR, Claude Code + Claude Desktop can call the graph via either
mechanism with zero new glue code.

## Scope

**In**

- Four tools, each a `ToolHandler` subclass:
  - `GetNodeTool` — returns a single node by id (or fuzzy name match).
  - `GetNeighborsTool` — returns neighbors filtered by `EdgeKind`.
  - `ShortestPathTool` — NetworkX shortest path between two node ids.
  - `BlastRadiusTool` — wraps PR-03's `blast_radius`.
- MCP server at `mcp/server.py` — stdio JSON-RPC, exposes the four tools.
- PreToolUse hook at `hooks/pretooluse.py` — detects `Read` / `Glob` / `Grep`
  tool calls, prepends `GRAPH_REPORT.md` contents to the agent context if the
  report exists and hasn't been injected yet this session.
- Guardrail wiring: `ToolAllowlistGuardrail` (only the 4 tools) +
  `PathGuardrail` (restrict to `.pyarnes/` and indexed roots).
- Unit tests + pexpect-based MCP smoke test.

**Out**

- Scorers + evals proving the token-reduction claim — PR-05.
- `/overview`, `/impact`, `/patch`, `/ship` skill files — PR-06.
- Adding the hook to `template/.claude/settings.json` — PR-06.

## Files

### New

- `packages/graph/src/pyarnes_graph/tools/__init__.py`
- `packages/graph/src/pyarnes_graph/tools/get_node_tool.py`
- `packages/graph/src/pyarnes_graph/tools/get_neighbors_tool.py`
- `packages/graph/src/pyarnes_graph/tools/shortest_path_tool.py`
- `packages/graph/src/pyarnes_graph/tools/blast_radius_tool.py`
- `packages/graph/src/pyarnes_graph/tools/registry_factory.py` — helper
  `build_graph_registry(engine) -> ToolRegistry` that returns a pre-populated
  `ToolRegistry`. Callers (MCP server, user code) share one factory.
- `packages/graph/src/pyarnes_graph/mcp/__init__.py`
- `packages/graph/src/pyarnes_graph/mcp/server.py` — `async def main()`
  entrypoint + `python -m pyarnes_graph.mcp.server` invocation.
- `packages/graph/src/pyarnes_graph/hooks/__init__.py`
- `packages/graph/src/pyarnes_graph/hooks/pretooluse.py` — hook entrypoint
  compatible with Claude Code's `.claude/settings.json` hook contract.
- `tests/unit/graph/test_tools.py` — each tool unit-tested against a fixture
  DB. `LLMRecoverableError` raised for missing nodes.
- `tests/unit/graph/test_mcp_server.py` — pexpect-based smoke: spawn
  `python -m pyarnes_graph.mcp.server`, send `tools/list` JSON-RPC, assert
  four tools returned.
- `tests/unit/graph/test_pretooluse_hook.py` — simulate a `Read` event,
  assert the hook emits a report-injection payload exactly once per session.

### Modified

- `packages/graph/pyproject.toml` — add `mcp>=1.0` (official MCP Python SDK).
- `packages/graph/src/pyarnes_graph/__init__.py` — export the tool classes
  and `build_graph_registry`.

## Reuse

| Existing utility | File | Used for |
|---|---|---|
| `ToolHandler` ABC | `packages/core/.../types.py` | All four tools subclass this directly. One `execute` method each. |
| `ToolRegistry` | `packages/harness/.../tools/registry.py` | `build_graph_registry` returns an instance of this — callers get the same semantics as existing tools. |
| `AgentLoop._call_tool` retry loop | `packages/harness/.../loop.py` | MCP-surface tools benefit from the existing `TransientError` → exponential-backoff path. Rate-limit-like DB contention retries via the existing mechanism. |
| `LLMRecoverableError` | `packages/core/.../errors.py` | "Node not found" / "graph not indexed yet" are surfaced as recoverable tool errors so the model can adjust. |
| `UserFixableError` | same | "MCP server couldn't locate `.pyarnes/graph.db`" bubbles to the human. |
| `GuardrailChain` + `ToolAllowlistGuardrail` + `PathGuardrail` | `packages/guardrails/.../guardrails.py` | Wrap each tool via the existing `GuardrailChain`. No new guardrail classes. |
| `ToolCallLogger` / `CapturedOutput` | harness package | MCP server logs every request/response to the same JSONL stream as PR-02's indexer. |
| `get_logger` | core | Structured logs for MCP JSON-RPC frames. |
| `configure_logging(json=True, stream=sys.stderr)` | core | MCP demands stdout is reserved for JSON-RPC — this config is already correct out of the box. |

## Design notes

1. **Tool contract is narrow on purpose.** Four tools cover 100% of the
   planned skills (`/overview`, `/impact`, `/patch`, `/ship`). Adding a fifth
   without a concrete use case is explicitly out of scope.
2. **Fuzzy name match in `GetNodeTool`** falls back to
   `GraphNode.name == query` when `query::node_id` doesn't match exactly. The
   top-3 candidates are returned when no exact hit — the model picks or
   refines. Implements "model can recover" pattern via
   `LLMRecoverableError` for zero matches.
3. **MCP server is thin.** `mcp/server.py` uses the `mcp` SDK's
   `Server.list_tools` / `Server.call_tool` decorators. Each decorator body
   delegates straight to the same `ToolHandler` instances used by
   `AgentLoop` — one code path, two transports.
4. **PreToolUse hook is idempotent per session.** Tracks injection state in
   `.pyarnes/session/<session-id>/report-injected.flag`. If the flag exists,
   hook returns quickly without re-reading the report. Matches "single-shot"
   semantics — Read/Glob/Grep calls after the first don't re-inject.
5. **Report freshness check.** Hook checks `GRAPH_REPORT.md` mtime against
   the newest indexed file in `IndexMeta`. If stale, emits a warning to
   stderr and injects anyway (model can still use stale context).
6. **stdout / stderr discipline.** MCP server writes JSON-RPC to stdout and
   logs to stderr via the existing `configure_logging(stream=sys.stderr)` —
   matches `CLAUDE.md`'s rule.

## Acceptance

```bash
# Tools from Python
python -c "
import asyncio
from pyarnes_graph.store.engine import create_engine
from pyarnes_graph.tools.registry_factory import build_graph_registry

async def main():
    engine = await create_engine('.pyarnes/graph.db')
    registry = build_graph_registry(engine)
    tool = registry.get('blast_radius')
    result = await tool.execute({'node_id': 'pyarnes_graph/schema.py::GraphNode'})
    print(result)

asyncio.run(main())
"

# MCP server smoke (pexpect-based test replicates this)
python -m pyarnes_graph.mcp.server <<< '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

# Hook (manual)
echo '{"event":"PreToolUse","tool":"Read","arguments":{"path":"foo.py"}}' \
  | python -m pyarnes_graph.hooks.pretooluse
# Expected: JSON payload containing the report contents, exit 0.
```

Unit checks:

- `test_tools.py` — per-tool tests for happy path, missing node
  (`LLMRecoverableError`), and allowlist guardrail blocks disallowed tools.
- `test_mcp_server.py` — pexpect spawn + `tools/list` + `tools/call`; asserts
  response payload structure.
- `test_pretooluse_hook.py` — first Read injects; second Read doesn't; stale
  report emits a stderr warning.

## Risks & rollback

- **Risk**: MCP SDK API churn. **Mitigation**: pin `mcp>=1.0,<2.0` and isolate
  the SDK surface behind `mcp/server.py` so version upgrades are a single-file
  change.
- **Risk**: Hook slows the first Read call visibly. **Mitigation**: hook is
  sync-fast (reads a single Markdown file, ≤ 50ms) and caches per session.
- **Rollback**: revert this PR; the indexer and analytics remain usable via
  direct Python imports. No adopter has wired up the hook yet (PR-06).

## Exit criteria

- [ ] All four tools return correct results against the PR-02 fixture DB.
- [ ] Allowlist + path guardrails block out-of-scope calls.
- [ ] MCP smoke test passes in pexpect.
- [ ] PreToolUse hook is idempotent per session and injects on first call.
- [ ] `uv run tasks check` green.
