"""Token burn types — objective, provider-agnostic data records.

Excluded intentionally: pricing logic, FX conversion, UI formatting.
Cost calculation lives in costing.py; these types carry only facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

__all__ = [
    "Cost",
    "SessionBurn",
    "SessionMetadata",
    "TokenUsage",
]


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Immutable token count record for one or more model turns.

    Addable so session-level aggregation stays mutation-free.
    Cache tokens are tracked separately because their pricing differs
    from plain input/output; see CostCalculator for the multipliers.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0  # prompt-cache write tokens
    cache_read_tokens: int = 0      # prompt-cache read tokens

    @property
    def total_tokens(self) -> int:
        """Input + output only — cache excluded (use CostCalculator for cost)."""
        return self.input_tokens + self.output_tokens

    def __add__(self, other: TokenUsage) -> TokenUsage:
        """Return the element-wise sum of two TokenUsage records."""
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_creation_tokens=self.cache_creation_tokens + other.cache_creation_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
        )

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass(frozen=True, slots=True)
class Cost:
    """Monetary cost with an explicit currency code.

    Separate from TokenUsage because cost depends on a pricing model
    that may be absent, wrong, or desired in a different denomination.
    Token counts are always objective; monetary cost is not.

    FX conversion is the caller's responsibility::

        eur = Cost(cost.amount * Decimal("0.92"), "EUR")
    """

    amount: Decimal  # raw amount from the CostCalculator
    currency: str    # ISO 4217 — "USD", "EUR", "GBP", …

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict."""
        return {"amount": str(self.amount), "currency": self.currency}


@dataclass(frozen=True, slots=True)
class SessionMetadata:
    """Provider-supplied identifiers attached to a session.

    All fields are plain strings so serialisation is trivial
    and no field references a specific tool or provider by type.
    """

    tool: str          # coding-assistant identifier
    ai_provider: str   # API-provider identifier
    model_id: str      # exact model string from the session file
    model_family: str  # high-level family derived from model_id


@dataclass(frozen=True, slots=True)
class SessionBurn:
    """Aggregated token and cost data for a single coding session."""

    session_id: str
    project: str               # derived from on-disk directory name
    metadata: SessionMetadata
    start_time: str            # ISO-8601 of first model turn
    end_time: str              # ISO-8601 of last model turn
    turns: int                 # count of model responses
    usage: TokenUsage
    cost: Cost | None = None   # None when no CostCalculator was supplied

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict (suitable for JSONL logging)."""
        return {
            "session_id": self.session_id,
            "project": self.project,
            "tool": self.metadata.tool,
            "ai_provider": self.metadata.ai_provider,
            "model_id": self.metadata.model_id,
            "model_family": self.metadata.model_family,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "turns": self.turns,
            "usage": self.usage.as_dict(),
            "cost": self.cost.as_dict() if self.cost else None,
        }
