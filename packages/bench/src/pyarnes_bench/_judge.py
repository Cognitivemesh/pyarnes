"""LLM-as-judge helper — call a ``ModelClient`` and parse a Pydantic model.

This module is private. It exists so ``race.py`` and ``fact.py`` share
one retry / error-mapping policy for every judge call:

* Extract the model's textual content from the ``next_action`` payload.
* Validate the JSON body against a caller-supplied Pydantic model via
  :class:`pydantic.TypeAdapter`.
* On ``ValidationError`` or non-JSON output, retry **once** (Stripe-
  style cap of 2), then raise :class:`pyarnes_core.errors.LLMRecoverableError`
  so the caller can feed the failure back to the model.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, TypeAdapter, ValidationError

from pyarnes_core.errors import LLMRecoverableError
from pyarnes_core.observe.logger import get_logger
from pyarnes_core.types import ModelClient

__all__ = [
    "judge_json",
]

logger = get_logger(__name__)

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _extract_text(payload: dict[str, Any]) -> str:
    """Pull the textual content out of a ``next_action`` return value.

    The ``ModelClient`` Protocol is loose: providers return slightly
    different shapes. We accept the two that matter in practice:
    ``{"content": str}`` and ``{"content": {"text": str}}``.
    """
    content = payload.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, dict) and isinstance(content.get("text"), str):
        return content["text"]
    raise LLMRecoverableError(
        message="judge response has no textual content",
        context={"payload_keys": sorted(payload.keys())},
    )


def _strip_fence(text: str) -> str:
    """Return the body of a ```...``` fence if present, else ``text``."""
    match = _FENCE_RE.search(text)
    return match.group(1) if match else text


async def judge_json[ModelT: BaseModel](
    client: ModelClient,
    prompt: str,
    model: type[ModelT],
    *,
    max_attempts: int = 2,
) -> ModelT:
    """Ask the judge for a JSON answer and parse it into ``model``.

    Args:
        client: Any ``ModelClient`` (structural Protocol).
        prompt: Rendered user-turn prompt.
        model: A ``pydantic.BaseModel`` subclass to validate against.
        max_attempts: Upper bound on judge invocations (default 2 —
            matches the harness retry cap documented in
            ``pyarnes_core.errors``).

    Returns:
        A validated instance of ``model``.

    Raises:
        LLMRecoverableError: If every attempt fails to produce JSON
            that validates against ``model``. Callers surface this to
            the outer harness, which feeds it back to the LLM as a
            ToolMessage.
    """
    adapter: TypeAdapter[ModelT] = TypeAdapter(model)
    messages = [{"role": "user", "content": prompt}]
    last_error: str = ""

    for attempt in range(1, max_attempts + 1):
        payload = await client.next_action(messages)
        try:
            raw = _strip_fence(_extract_text(payload))
            return adapter.validate_json(raw)
        except (ValidationError, ValueError) as exc:
            last_error = str(exc)
            logger.warning(
                "judge.parse_failed attempt={attempt} model={model} error={error}",
                attempt=attempt,
                model=model.__name__,
                error=last_error[:200],
            )

    raise LLMRecoverableError(
        message=f"judge produced invalid JSON for {model.__name__} after {max_attempts} attempts",
        context={"last_error": last_error[:500], "model": model.__name__},
    )
