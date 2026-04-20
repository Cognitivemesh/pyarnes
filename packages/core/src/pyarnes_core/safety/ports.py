"""Safety domain ports — abstract guardrail contract.

Structural type used by ``pyarnes_guardrails.GuardrailChain``. The
original ``Guardrail`` ABC lives in the guardrails package for backward
compatibility; this Protocol captures the same contract without forcing
subclassing.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = [
    "GuardrailPort",
]


@runtime_checkable
class GuardrailPort(Protocol):
    """Structural contract for a single guardrail check.

    Implementations raise ``UserFixableError`` on violation and return
    ``None`` when the call is allowed.
    """

    def check(self, tool_name: str, arguments: dict[str, Any]) -> None:
        """Raise ``UserFixableError`` if the call violates this guardrail."""
        ...
