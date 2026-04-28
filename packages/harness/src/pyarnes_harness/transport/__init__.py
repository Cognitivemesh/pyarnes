"""Provider transport adapters for pyarnes-harness.

Concrete adapters (LiteLLM, Anthropic, OpenAI) defer their SDK imports so the
harness package does not force those SDKs as hard dependencies.
"""

from __future__ import annotations

from pyarnes_harness.transport.anthropic import AnthropicTransport
from pyarnes_harness.transport.litellm import LiteLLMTransport
from pyarnes_harness.transport.openai import OpenAITransport
from pyarnes_harness.transport.ports import (
    NormalizedResponse,
    NormalizedToolCall,
    ProviderTransport,
    TransportModelClient,
)

__all__ = [
    "AnthropicTransport",
    "LiteLLMTransport",
    "NormalizedResponse",
    "NormalizedToolCall",
    "OpenAITransport",
    "ProviderTransport",
    "TransportModelClient",
]
