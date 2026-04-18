"""Project-specific guardrails for the PII pipeline."""

from __future__ import annotations

from pyarnes_core.errors import UserFixableError
from pyarnes_guardrails import Guardrail


class PiiLeakGuardrail(Guardrail):
    """Reject ``render_markdown`` calls whose text still contains PII tokens.

    This is the belt-and-braces check after ``redact_pii`` has already run.
    A real deployment would run a second Presidio pass; we keep the
    fixture-level contract by scanning for known tokens.
    """

    def check(self, tool_name: str, arguments: dict) -> None:
        if tool_name != "render_markdown":
            return
        text = str(arguments.get("text", ""))
        for forbidden in ("@example.com",):
            if forbidden in text:
                raise UserFixableError(
                    message=f"render_markdown input still contains PII token {forbidden!r}",
                    prompt_hint="Run redact_pii again before rendering.",
                )
