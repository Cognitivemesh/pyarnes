"""JSON-serialization atoms.

Centralizes the ``default=str, ensure_ascii=False`` pattern so every
site that writes a JSON line uses identical behavior. Addresses D17
(``CapturedOutput.as_dict`` lossy-stringifies values) and D18
(``ToolCallEntry.result: str`` forces structure loss).
"""

from __future__ import annotations

import json
from typing import Any

__all__ = [
    "dumps",
    "to_jsonable",
]

_NATIVE_JSON_TYPES = (dict, list, tuple, str, int, float, bool, type(None))


def to_jsonable(value: Any) -> Any:
    """Return *value* unchanged when JSON-native; otherwise ``str(value)``.

    Lets dataclasses hold structured payloads (dicts, lists) without
    prematurely stringifying them at the capture boundary. Final
    serialization happens once, at the write site, via :func:`dumps`.

    Args:
        value: Any Python value.

    Returns:
        *value* unchanged for native JSON types, otherwise ``str(value)``.
    """
    if isinstance(value, _NATIVE_JSON_TYPES):
        return value
    return str(value)


def dumps(value: Any) -> str:
    """Canonical JSON serializer for the harness.

    Args:
        value: Value to serialize.

    Returns:
        A JSON string with ``default=str`` (non-serializable objects
        fall through to their repr) and ``ensure_ascii=False`` (Unicode
        preserved).
    """
    return json.dumps(value, default=str, ensure_ascii=False)
