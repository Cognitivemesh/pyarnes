# Harness Feature Expansion

Inspired by NousResearch/hermes-agent (H1–H10) and badlogic/pi-mono (P1–P10,
P5 excluded). 19 features across 5 phases. All code is async-first; litellm
is always a deferred import.

---

## Phase 1 — Safety & Loop Control ✅

| ID | Feature | New file | Modified |
|----|---------|----------|---------|
| H6 | Message sanitization pipeline | `core/safety/sanitize.py` | `loop.py` |
| H9 | Credential redactor | `core/safety/redact.py` | `capture/tool_log.py`, `loop.py` |
| H8 | Prompt injection defense | `core/safety/injection.py` | `guardrails/guardrails.py` |
| H4 | IterationBudget | `harness/budget.py` | `loop.py` (LoopConfig.budget) |
| H10 | Self-registering `@tool` decorator | — | `tools/registry.py`, `runtime.py` |
| P6 | Terminate hint (`{"terminate": True}`) | — | `loop.py`, `ToolMessage.terminate` |

**Key design decisions:**
- `sanitize_messages()` is called on the copy passed to `model.next_action()`,
  not on the stored history — keeps raw content intact for replay.
- `redact_dict` is the default `redactor` in `ToolCallLogger.__init__` — opt
  out by passing `redactor=None`.
- `InjectionGuardrail` raises `LLMRecoverableError` (not `UserFixableError`)
  so the model self-corrects without interrupting the human.
- `IterationBudget` is shared via reference — pass the same instance to parent
  and sub-agents.
- `use_global_registry=True` on `AgentRuntime` merges `@tool`-decorated classes
  with any explicitly passed tools; explicit tools take precedence.

---

## Phase 2 — Loop Hooks & Error Intelligence

| ID | Feature | New file | Modified |
|----|---------|----------|---------|
| P4 | `beforeToolCall` / `afterToolCall` hooks | `harness/hooks.py` | `loop.py`, `runtime.py` |
| H5 | Error classifier | `harness/classifier.py` | `loop.py` |
| P7 | Steering / follow-up message queue | `harness/steering.py` | `loop.py`, `runtime.py` |

**Key design decisions:**
- `PreToolHook` returns modified args or `None` (unchanged); raising
  `LLMRecoverableError` vetoes the call.
- `PostToolHook` receives raw result and `is_error`; its return value replaces
  the result fed to `ToolMessage`.
- `ClassifiedError.should_compress` emits `loop.context_too_long` event;
  Phase 3 compactor subscribes to it.
- `SteeringQueue.drain()` inserts notes at the top of each iteration —
  no lock contention with the running tool.

---

## Phase 3 — Context Management

| ID | Feature | New file | Modified |
|----|---------|----------|---------|
| P2 | Layered message transformation | `harness/transform.py` | `loop.py`, `runtime.py` |
| P1+P9 | Token-budget compaction + split-turn | `harness/compaction.py` | — |
| H1 | ContextCompressor (auto-trigger) | `harness/compressor.py` | `runtime.py` |

**Key design decisions:**
- `TransformChain.apply()` is called on a fresh copy each iteration; the stored
  `messages` list is never mutated by transformers.
- `_find_cut_index` scans backward and never cuts inside a tool-call/tool-result
  pair to prevent orphaned tool results.
- Anti-thrash guard: skip compaction if savings < `min_savings_ratio` (default 10 %).
- `ContextCompressor.with_compressor()` classmethod on `AgentRuntime` is the
  recommended one-liner for adopters.

---

## Phase 4 — Provider Abstraction

| ID | Feature | New file | Modified |
|----|---------|----------|---------|
| H2+P10 | Multi-provider transport + schema conversion | `harness/transport/` | `tools/registry.py` |
| H3 | Tool-call JSON repair | `harness/repair.py` | `transport/litellm.py` |

**Key design decisions:**
- `TransportModelClient` adapts `ProviderTransport` → `ModelClient` protocol —
  `AgentLoop` requires zero changes.
- `ToolRegistry.register_schema()` is optional; tools that don't register a
  schema are excluded from auto-conversion.
- `repair_json_args` raises `LLMRecoverableError` on unrepaired JSON so the
  model can re-emit a clean call.
- litellm import is deferred inside `LiteLLMTransport.complete()`.

---

## Phase 5 — Concurrency & Session Management

| ID | Feature | New file | Modified |
|----|---------|----------|---------|
| H7 | Parallel tool batch detection | `harness/parallel.py` | `loop.py` |
| P3 | Session branching with JSONL parent refs | — | `capture/tool_log.py` |
| P8 | Partial/streaming JSON argument parsing | — | `transport/ports.py`, `transport/litellm.py` |

**Key design decisions:**
- `can_parallelize` is conservative: any shared path arg → serial; any tool in
  `SERIAL_TOOLS` → serial.
- `ToolCallEntry.parent_id` defaults to `None`; no migration needed for
  existing logs.
- `StreamingProviderTransport` is an optional sub-protocol; non-streaming
  transports are unaffected.

---

## Constraints (all phases)

- `pyarnes_core` has zero imports from `pyarnes_harness`.
- No circular imports between new modules.
- Every public symbol in `__init__.py`.
- TDD: Red → Green → Refactor per feature.
- `uv run tasks check` must pass before each phase merge.
