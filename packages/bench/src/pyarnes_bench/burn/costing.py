"""Cost calculation — maps model ID + TokenUsage to a monetary Cost.

Excluded: FX conversion, pricing-table maintenance, caching of rates.

LiteLLM is the backing store for LiteLLMCostCalculator because it ships
pricing for most hosted models and updates its table with each release.
Alternative considered: hardcoded dict — rejected because it creates a
maintenance burden every time a model is added or repriced.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from pyarnes_bench.burn.types import Cost, TokenUsage

__all__ = [
    "CostCalculator",
    "LiteLLMCostCalculator",
]


class CostCalculator(Protocol):
    """Structural contract: price a model + usage into a Cost.

    Any object with a matching ``calculate`` signature satisfies this
    Protocol — no inheritance required.
    """

    def calculate(self, model_id: str, usage: TokenUsage) -> Cost | None:
        """Return a Cost, or None if model_id is unrecognised.

        Args:
            model_id: Exact model identifier string from the session.
            usage: Token counts to price.

        Returns:
            A ``Cost`` with amount and currency, or ``None`` when the
            model is not in the calculator's price list.
        """
        ...


class LiteLLMCostCalculator:
    """Prices token usage via LiteLLM's built-in model cost table.

    Cache token pricing applied via Anthropic's documented multipliers.
    These multipliers are hardcoded here because LiteLLM's
    ``model_cost`` dict does not expose them directly.

    Args:
        currency: ISO 4217 code stored on returned ``Cost`` objects.
            The numeric amount mirrors LiteLLM's output (typically USD).
            To convert, apply your own exchange rate::

                raw = calc.calculate(model_id, usage)
                eur = Cost(raw.amount * Decimal("0.92"), "EUR")
    """

    def __init__(self, currency: str = "USD") -> None:
        """Initialise the calculator with an ISO 4217 currency code."""
        self._currency = currency

    def calculate(self, model_id: str, usage: TokenUsage) -> Cost | None:
        """Look up model pricing via LiteLLM and compute total cost.

        Args:
            model_id: Exact model identifier.
            usage: Token breakdown to price.

        Returns:
            A ``Cost``, or ``None`` if LiteLLM does not know the model.
        """
        try:
            import litellm  # deferred: keeps litellm optional at module load time  # noqa: PLC0415

            pricing = litellm.model_cost.get(model_id)
        except ImportError:
            return None

        if pricing is None:
            return None

        inp_rate: float = pricing.get("input_cost_per_token", 0.0)
        out_rate: float = pricing.get("output_cost_per_token", 0.0)

        raw = (
            usage.input_tokens * inp_rate
            + usage.output_tokens * out_rate
            + usage.cache_creation_tokens * inp_rate * 1.25  # Anthropic cache-write pricing multiplier
            + usage.cache_read_tokens * inp_rate * 0.10  # Anthropic cache-read pricing multiplier
        )
        return Cost(amount=Decimal(str(raw)), currency=self._currency)
