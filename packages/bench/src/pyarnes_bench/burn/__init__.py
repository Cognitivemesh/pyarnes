"""pyarnes-burn — token cost tracking for AI coding sessions.

Reads provider session files (v1: JSONL only) and surfaces token consumption
as an evaluation axis inside ``pyarnes-bench``. Lite port of
``getagentseal/codeburn``, scoped to evaluation use-cases.

Excluded intentionally: dashboard UI, FX conversion, trend analytics,
deduplication across provider sessions. These belong in a full codeburn
integration, not an evaluation sub-library.

Extension point: subclass ``JsonlProvider`` (six hooks) to add any
JSONL-based tool; subclass ``Provider`` directly for SQL/binary formats.
"""

from __future__ import annotations

from pyarnes_bench.burn.claude_code import ClaudeCodeProvider
from pyarnes_bench.burn.costing import CostCalculator, LiteLLMCostCalculator
from pyarnes_bench.burn.provider import BurnTracker, JsonlProvider, Provider
from pyarnes_bench.burn.types import Cost, SessionBurn, SessionMetadata, TokenUsage

__all__ = [
    "BurnTracker",
    "ClaudeCodeProvider",
    "Cost",
    "CostCalculator",
    "JsonlProvider",
    "LiteLLMCostCalculator",
    "Provider",
    "SessionBurn",
    "SessionMetadata",
    "TokenUsage",
]
