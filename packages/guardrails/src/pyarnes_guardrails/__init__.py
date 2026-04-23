"""pyarnes-guardrails — composable safety guardrails.

Guardrails wrap tool execution and enforce limits on what the system can
touch.  They are composable — stack multiple guardrails via ``GuardrailChain``.

* **PathGuardrail** — block paths outside allowed roots.
* **CommandGuardrail** — block dangerous shell commands.
* **ToolAllowlistGuardrail** — permit only pre-approved tools.
* **SemanticGuardrail** — LLM-judged intent and appropriateness check.
* **GuardrailChain** — run a sequence; fail on the first violation.
"""

from __future__ import annotations

from pyarnes_guardrails.guardrails import (
    AsyncGuardrail,
    CommandGuardrail,
    Guardrail,
    GuardrailChain,
    PathGuardrail,
    ToolAllowlistGuardrail,
)
from pyarnes_guardrails.semantic import SemanticGuardrail

__all__ = [
    "AsyncGuardrail",
    "CommandGuardrail",
    "Guardrail",
    "GuardrailChain",
    "PathGuardrail",
    "SemanticGuardrail",
    "ToolAllowlistGuardrail",
]

from pyarnes_core.packaging import version_of

__version__ = version_of("pyarnes-guardrails")
