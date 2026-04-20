"""pyarnes-harness — runtime engine for the agentic harness.

This package contains the runtime components that drive agent execution:

* **loop** — ``AgentLoop`` with structured error routing.
* **guardrails** — composable safety checks (path, command, tool-allowlist).
* **tools** — ``ToolRegistry`` for handler discovery and validation.
* **capture** — ``OutputCapture`` and ``ToolCallLogger`` for full observability.
"""

from __future__ import annotations

from pyarnes_harness.capture.output import CapturedOutput, OutputCapture
from pyarnes_harness.capture.tool_log import ToolCallEntry, ToolCallLogger
from pyarnes_harness.guardrails import (
    CommandGuardrail,
    Guardrail,
    GuardrailChain,
    PathGuardrail,
    ToolAllowlistGuardrail,
)
from pyarnes_harness.loop import AgentLoop, LoopConfig, ToolMessage
from pyarnes_harness.tools.registry import ToolRegistry

__all__ = [
    "AgentLoop",
    "CapturedOutput",
    "CommandGuardrail",
    "Guardrail",
    "GuardrailChain",
    "LoopConfig",
    "OutputCapture",
    "PathGuardrail",
    "ToolAllowlistGuardrail",
    "ToolCallEntry",
    "ToolCallLogger",
    "ToolMessage",
    "ToolRegistry",
]

from pyarnes_core.packaging import version_of

__version__ = version_of("pyarnes-harness")
