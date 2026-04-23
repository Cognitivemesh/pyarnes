"""Sanitise Claude Code ``session_id`` before using it to build a path.

The hook event JSON comes from a process that is itself driven by an
LLM. If the model (or a malicious tool response that smuggled content
back up) controls ``session_id`` and we ``f"checkpoint-{session_id}"``
the string straight into a Path, an attacker can trivially escape the
state directory: ``session_id = "../../../.bashrc"``.

:func:`safe_session_id` is the one allowed way a hook turns an event-
supplied session_id into a path fragment. It accepts only the shape
Anthropic's documentation uses for real session ids — 1..64 characters
from ``[A-Za-z0-9._-]`` — and falls back to the literal ``"default"``
otherwise. The fallback is chosen to collide with the default pool so a
tampered event simply lands in the shared file instead of opening a
write-anywhere primitive.
"""

from __future__ import annotations

import re

__all__ = ["safe_session_id"]

_SAFE = re.compile(r"\A[A-Za-z0-9._-]{1,64}\Z")
# A string that is only dots — ".", "..", "..." — is a directory
# traversal primitive and must never be used as a path fragment.
_ONLY_DOTS = re.compile(r"\A\.+\Z")


def safe_session_id(raw: object) -> str:
    """Return *raw* if it is a safe id, else the literal ``"default"``."""
    if not isinstance(raw, str):
        return "default"
    if _ONLY_DOTS.match(raw):
        return "default"
    if not _SAFE.match(raw):
        return "default"
    return raw
