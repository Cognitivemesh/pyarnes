"""Guardrail validation endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from pyarnes_api.schemas import GuardrailCheckRequest, GuardrailCheckResponse
from pyarnes_core.errors import UserFixableError
from pyarnes_guardrails import (
    CommandGuardrail,
    GuardrailChain,
    PathGuardrail,
)

router = APIRouter(tags=["guardrails"])

# Default guardrail chain — can be reconfigured at startup.
_chain = GuardrailChain(
    guardrails=[
        PathGuardrail(allowed_roots=("/workspace",)),
        CommandGuardrail(),
    ]
)


@router.post(
    "/guardrails/check",
    response_model=GuardrailCheckResponse,
    summary="Validate a tool call against guardrails",
)
async def check_guardrails(body: GuardrailCheckRequest) -> GuardrailCheckResponse:
    """Run the configured guardrail chain on a tool call.

    Returns whether the call is allowed and, if not, the violation message.
    """
    try:
        _chain.check(body.tool_name, body.arguments)
    except UserFixableError as exc:
        return GuardrailCheckResponse(allowed=False, violation=str(exc))
    return GuardrailCheckResponse(allowed=True)
