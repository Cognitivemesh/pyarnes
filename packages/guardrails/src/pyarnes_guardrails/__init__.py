"""pyarnes-guardrails — composable safety guardrails.

Guardrails wrap tool execution and enforce limits on what the system can
touch.  They are composable — stack multiple guardrails via ``GuardrailChain``.

Original set:

* **PathGuardrail** — block paths outside allowed roots.
* **CommandGuardrail** — block dangerous shell commands.
* **ToolAllowlistGuardrail** — permit only pre-approved tools.
* **SemanticGuardrail** — LLM-judged intent and appropriateness check.
* **GuardrailChain** — run a sequence; fail on the first violation.

Cross-CLI additions (reachable from the Claude Code hook surface):

* **SecretLeakGuardrail** — detect plaintext secrets in tool arguments
  (PreToolUse) or output (PostToolUse).
* **NetworkEgressGuardrail** — block URLs whose host is not on the
  allowlist (PreToolUse for ``Bash`` / ``WebFetch``).
* **RateLimitGuardrail** — deny calls that exceed a per-tool sliding
  window (PreToolUse, disk-backed state).
* **Violation** / ``append_violation`` — sidecar JSONL writer so the
  bench ``GuardrailComplianceScorer`` can grade a session post-hoc.
"""

from __future__ import annotations

from pyarnes_guardrails.benchmark_gate import BenchmarkGateGuardrail
from pyarnes_guardrails.guardrails import (
    ASTGuardrail,
    AsyncGuardrail,
    CommandGuardrail,
    Guardrail,
    GuardrailChain,
    InjectionGuardrail,
    PathGuardrail,
    ToolAllowlistGuardrail,
)
from pyarnes_guardrails.network_egress import NetworkEgressGuardrail
from pyarnes_guardrails.rate_limit import RateLimitGuardrail
from pyarnes_guardrails.secret_leak import SecretLeakGuardrail
from pyarnes_guardrails.semantic import SemanticGuardrail
from pyarnes_guardrails.violation_log import (
    Violation,
    append_violation,
    default_violation_log_path,
)

__all__ = [
    "ASTGuardrail",
    "AsyncGuardrail",
    "BenchmarkGateGuardrail",
    "CommandGuardrail",
    "Guardrail",
    "GuardrailChain",
    "InjectionGuardrail",
    "NetworkEgressGuardrail",
    "PathGuardrail",
    "RateLimitGuardrail",
    "SecretLeakGuardrail",
    "SemanticGuardrail",
    "ToolAllowlistGuardrail",
    "Violation",
    "append_violation",
    "default_violation_log_path",
]

from pyarnes_core.packaging import version_of

__version__ = version_of("pyarnes-guardrails")
