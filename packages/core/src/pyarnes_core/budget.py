"""Per-session call / time / token budget.

The enforcement primitive used by the Claude Code ``PostToolUse`` and
``Stop`` hooks (and by the in-process ``AgentLoop`` when the adopter
opts in). Claude Code does not expose a native turn or token cap — a
``Stop`` hook returning ``{"continue": false}`` is the only mechanism
that ends a session mid-flight, and ``Budget.consume`` is the primitive
the hook asks.

Token accounting is best-effort: the hook pulls ``input_tokens`` /
``output_tokens`` off the CC session transcript when they are present
(they are, on current CC releases), but the JSONL schema is not
documented, so callers that want deterministic enforcement should rely
on the ``calls`` and ``seconds`` caps instead.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from pyarnes_core.errors import UserFixableError

__all__ = ["Budget"]


@dataclass(frozen=True, slots=True)
class Budget:
    """Immutable budget cap + running totals.

    Attributes:
        max_calls: Upper bound on tool calls. ``None`` disables the cap.
        max_seconds: Upper bound on cumulative wall time. ``None`` disables.
        max_tokens: Upper bound on total tokens (input + output).
            ``None`` disables — useful when the transcript schema does
            not expose token usage.
        calls: Calls consumed so far.
        seconds: Wall seconds consumed so far.
        tokens: Tokens consumed so far.
    """

    max_calls: int | None = None
    max_seconds: float | None = None
    max_tokens: int | None = None
    calls: int = 0
    seconds: float = 0.0
    tokens: int = 0

    def consume(
        self,
        *,
        calls: int = 1,
        seconds: float = 0.0,
        tokens: int = 0,
    ) -> Budget:
        """Return a new ``Budget`` with the given quantities added.

        Args:
            calls: Tool calls to record.
            seconds: Wall seconds to add.
            tokens: Tokens (input + output) to add.

        Returns:
            A fresh ``Budget`` with updated counters.
        """
        return replace(
            self,
            calls=self.calls + calls,
            seconds=self.seconds + seconds,
            tokens=self.tokens + tokens,
        )

    def is_exhausted(self) -> bool:
        """Return ``True`` when any configured cap has been hit."""
        return self.exceeded_cap() is not None

    def exceeded_cap(self) -> str | None:
        """Return the name of the first exceeded cap, or ``None``."""
        if self.max_calls is not None and self.calls >= self.max_calls:
            return "calls"
        if self.max_seconds is not None and self.seconds >= self.max_seconds:
            return "seconds"
        if self.max_tokens is not None and self.tokens >= self.max_tokens:
            return "tokens"
        return None

    def raise_if_exhausted(self) -> None:
        """Raise ``UserFixableError`` when any cap is hit.

        Callers in a ``Stop`` hook should instead emit
        ``{"continue": false, ...}`` directly — this method is aimed at
        in-process loops that already understand the error taxonomy.
        """
        cap = self.exceeded_cap()
        if cap is None:
            return
        raise UserFixableError(
            message=f"Budget cap '{cap}' exceeded: {self.as_dict()}",
            prompt_hint="Raise the cap or end the session.",
        )

    def as_dict(self) -> dict[str, Any]:
        """Plain-dict form for JSON persistence."""
        return {
            "max_calls": self.max_calls,
            "max_seconds": self.max_seconds,
            "max_tokens": self.max_tokens,
            "calls": self.calls,
            "seconds": self.seconds,
            "tokens": self.tokens,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Budget:
        """Inverse of :meth:`as_dict`."""
        return cls(
            max_calls=data.get("max_calls"),
            max_seconds=data.get("max_seconds"),
            max_tokens=data.get("max_tokens"),
            calls=int(data.get("calls", 0)),
            seconds=float(data.get("seconds", 0.0)),
            tokens=int(data.get("tokens", 0)),
        )
