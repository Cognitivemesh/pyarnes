"""Action-kind classifier.

Addresses B8: the loop only branches on ``type == "final_answer"`` and
treats every other shape as a tool call, producing empty-tool-name
dispatches that surface as ``"Unknown tool: "``. This atom gives the
loop a three-way decision: final-answer, tool-call, or recoverable
garbage (fed back to the model as an error message).
"""

from __future__ import annotations

from enum import Enum
from typing import Any

__all__ = [
    "ActionKind",
    "classify",
]


class ActionKind(Enum):
    """Discrete outcomes of classifying a model action."""

    FINAL_ANSWER = "final_answer"
    TOOL_CALL = "tool_call"
    UNKNOWN = "unknown"


_KIND_BY_TYPE: dict[str, ActionKind] = {
    ActionKind.FINAL_ANSWER.value: ActionKind.FINAL_ANSWER,
    ActionKind.TOOL_CALL.value: ActionKind.TOOL_CALL,
}


def classify(action: dict[str, Any]) -> ActionKind:
    """Return the :class:`ActionKind` of a model-produced action dict.

    Rules:

    * ``type == "final_answer"`` → ``FINAL_ANSWER``.
    * ``type == "tool_call"`` with a non-empty ``tool`` name →
      ``TOOL_CALL``.
    * Anything else → ``UNKNOWN`` (callers should surface this as an
      ``LLMRecoverableError`` so the model self-corrects).

    Args:
        action: The dict returned by ``ModelClient.next_action``.

    Returns:
        The classification.
    """
    kind = _KIND_BY_TYPE.get(action.get("type", ""), ActionKind.UNKNOWN)
    if kind is ActionKind.TOOL_CALL and not action.get("tool"):
        return ActionKind.UNKNOWN
    return kind
