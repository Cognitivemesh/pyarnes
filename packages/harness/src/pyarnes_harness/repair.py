"""Progressive JSON repair for tool-call arguments from LLMs.

Local/quantized models occasionally emit malformed JSON. This module tries a
sequence of cheap repairs before giving up and surfacing a recoverable error.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pyarnes_core.errors import LLMRecoverableError

_TRAILING_COMMA = re.compile(r",\s*(?=[}\]])")
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def repair_json_args(raw: str) -> dict[str, Any]:
    """Parse and repair JSON tool-call arguments.

    Tries in order: direct parse → strip trailing commas → close unclosed
    braces/brackets → strip control chars. Raises ``LLMRecoverableError`` if
    all repairs fail so the model can self-correct.
    """
    if not raw:
        raise LLMRecoverableError("tool-call arguments are empty")

    # Fast path
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Strip trailing commas before ] or }
    candidate = _TRAILING_COMMA.sub("", raw)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # Close unclosed braces and brackets
    closed = _close_open(candidate)
    try:
        return json.loads(closed)
    except json.JSONDecodeError:
        pass

    # Strip control characters and retry full pipeline
    clean = _CONTROL_CHARS.sub("", raw)
    candidate2 = _TRAILING_COMMA.sub("", clean)
    closed2 = _close_open(candidate2)
    try:
        return json.loads(closed2)
    except json.JSONDecodeError:
        pass

    raise LLMRecoverableError(f"cannot parse tool-call arguments: {raw[:120]!r}")


def _close_open(text: str) -> str:
    """Append missing closing braces and brackets."""
    stack: list[str] = []
    in_string = False
    escape_next = False
    for ch in text:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]" and stack:
            stack.pop()
    return text + "".join(reversed(stack))
