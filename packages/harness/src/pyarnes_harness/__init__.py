"""pyarnes-harness — runtime engine for the agentic harness.

This package contains the runtime components that drive agent execution:

* **loop** — ``AgentLoop`` with structured error routing.
* **guardrails** — composable safety checks (path, command, tool-allowlist).
* **tools** — ``ToolRegistry`` for handler discovery and validation.
* **capture** — ``OutputCapture`` and ``ToolCallLogger`` for full observability.
"""

from __future__ import annotations

from pyarnes_harness.budget import IterationBudget
from pyarnes_harness.capture.cc_session import read_cc_session, resolve_cc_session_path
from pyarnes_harness.capture.output import CapturedOutput, OutputCapture
from pyarnes_harness.capture.tool_log import ToolCallEntry, ToolCallLogger
from pyarnes_harness.classifier import ClassifiedError, classify_error
from pyarnes_harness.compaction import CompactionConfig, CompactionTransformer, compact
from pyarnes_harness.compressor import ContextCompressor
from pyarnes_harness.context import AgentContext
from pyarnes_harness.guardrails import (
    AsyncGuardrail,
    CommandGuardrail,
    Guardrail,
    GuardrailChain,
    InjectionGuardrail,
    PathGuardrail,
    SemanticGuardrail,
    ToolAllowlistGuardrail,
)
from pyarnes_harness.hooks import HookChain, PostToolHook, PreToolHook
from pyarnes_harness.loop import AgentLoop, LoopConfig, ToolMessage
from pyarnes_harness.repair import repair_json_args
from pyarnes_harness.runtime import AgentRuntime
from pyarnes_harness.steering import SteeringQueue
from pyarnes_harness.tools.registry import ToolRegistry, ToolSchema, global_registry, tool
from pyarnes_harness.transform import MessageTransformer, TransformChain
from pyarnes_harness.transport import (
    AnthropicTransport,
    LiteLLMTransport,
    NormalizedResponse,
    NormalizedToolCall,
    OpenAITransport,
    ProviderTransport,
    TransportModelClient,
)
from pyarnes_harness.verification import VerificationLoop, VerificationResult

__all__ = [
    "AgentContext",
    "AgentLoop",
    "AgentRuntime",
    "AnthropicTransport",
    "AsyncGuardrail",
    "CapturedOutput",
    "ClassifiedError",
    "CommandGuardrail",
    "CompactionConfig",
    "CompactionTransformer",
    "ContextCompressor",
    "Guardrail",
    "GuardrailChain",
    "HookChain",
    "InjectionGuardrail",
    "IterationBudget",
    "LiteLLMTransport",
    "LoopConfig",
    "MessageTransformer",
    "NormalizedResponse",
    "NormalizedToolCall",
    "OpenAITransport",
    "OutputCapture",
    "PathGuardrail",
    "PostToolHook",
    "PreToolHook",
    "ProviderTransport",
    "SemanticGuardrail",
    "SteeringQueue",
    "ToolAllowlistGuardrail",
    "ToolCallEntry",
    "ToolCallLogger",
    "ToolMessage",
    "ToolRegistry",
    "ToolSchema",
    "TransformChain",
    "TransportModelClient",
    "VerificationLoop",
    "VerificationResult",
    "classify_error",
    "compact",
    "global_registry",
    "read_cc_session",
    "repair_json_args",
    "resolve_cc_session_path",
    "tool",
]

from pyarnes_core.packaging import version_of

__version__ = version_of("pyarnes-harness")
