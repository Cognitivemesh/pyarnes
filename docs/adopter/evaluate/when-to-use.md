---
persona: adopter
tags: [adopter, evaluate, fit]
---

# When to use pyarnes

Use pyarnes when you want a **small, auditable harness** around tool-calling agents, and you want to own provider adapters, tool wiring, and safety posture directly.

| Option | Best fit | Trade-off vs pyarnes |
|---|---|---|
| **pyarnes** | Teams that want explicit contracts (`ModelClient`, `ToolHandler`) and composable guardrails | More assembly required; fewer batteries included |
| **LangGraph** | Complex graph/state orchestration with rich ecosystem integrations | Heavier abstraction and framework surface area |
| **AutoGen** | Multi-agent conversations and role-based collaboration patterns | Less “thin harness” control; opinionated agent flows |
| **smolagents** | Very fast prototyping with lightweight agent APIs | Less emphasis on strict lifecycle/guardrail composition |
| **CrewAI** | Team/workflow-style orchestration with task delegation ergonomics | Higher-level paradigm than a minimal loop |
| **Raw tool-calling loop** | Maximum custom behavior and zero framework coupling | You must build lifecycle, retries, logging, and guardrails yourself |

pyarnes sits between “raw loop” and “full framework.” It gives you a tested execution loop, explicit error taxonomy, structured JSONL logging, and opt-in guardrail composition without hiding core control flow. That makes it a strong choice when you need to explain and audit agent behavior in CI or production, but do not want to commit to a large orchestration DSL.

If you already need graph scheduling, long-lived shared memory primitives, or rich built-in agent topologies, higher-level frameworks can be a better default.
If you mostly need deterministic tool dispatch, bounded retries, and clear extension points, pyarnes is usually the simpler long-term maintenance choice.
