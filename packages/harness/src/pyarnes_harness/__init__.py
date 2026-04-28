"""pyarnes-harness — runtime engine for the agentic harness.

This package contains the runtime components that drive agent execution:

* **loop** — ``AgentLoop`` with structured error routing.
* **guardrails** — composable safety checks (path, command, tool-allowlist).
* **tools** — ``ToolRegistry`` for handler discovery and validation.
* **capture** — ``OutputCapture`` and ``ToolCallLogger`` for full observability.
"""

from __future__ import annotations

from pyarnes_harness.capture.cc_session import read_cc_session, resolve_cc_session_path
from pyarnes_harness.capture.output import CapturedOutput, OutputCapture
from pyarnes_harness.capture.tool_log import ToolCallEntry, ToolCallLogger
from pyarnes_harness.context import AgentContext
from pyarnes_harness.guardrails import (
    AsyncGuardrail,
    CommandGuardrail,
    Guardrail,
    GuardrailChain,
    PathGuardrail,
    SemanticGuardrail,
    ToolAllowlistGuardrail,
)
from pyarnes_harness.loop import AgentLoop, LoopConfig, ToolMessage
from pyarnes_harness.runtime import AgentRuntime
from pyarnes_harness.tools.registry import ToolRegistry
from pyarnes_harness.verification import VerificationLoop, VerificationResult

__all__ = [
    "AgentContext",
    "AgentLoop",
    "AgentRuntime",
    "AsyncGuardrail",
    "CapturedOutput",
    "CommandGuardrail",
    "Guardrail",
    "GuardrailChain",
    "LoopConfig",
    "OutputCapture",
    "PathGuardrail",
    "SemanticGuardrail",
    "ToolAllowlistGuardrail",
    "ToolCallEntry",
    "ToolCallLogger",
    "ToolMessage",
    "ToolRegistry",
    "VerificationLoop",
    "VerificationResult",
    "read_cc_session",
    "resolve_cc_session_path",
]

from pyarnes_core.packaging import version_of

__version__ = version_of("pyarnes-harness")
