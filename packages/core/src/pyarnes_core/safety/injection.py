"""Prompt injection detection — scan tool arguments for adversarial overrides.

Detects common prompt injection patterns in tool arguments and file content:
- Instruction override phrases ("ignore previous instructions", etc.)
- Hidden Unicode steering characters (RTLO, zero-width joiners)
- HTML/XML comment injection
- Exfiltration keyword clusters

Returns the matched pattern description so callers can surface a clear error.
Does not raise — callers decide how to act (guardrail, log, or reject).
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["INJECTION_PATTERNS", "detect_injection", "walk_for_injection"]

# Each entry: (human-readable label, compiled pattern)
INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Instruction override
    (
        "instruction-override",
        re.compile(
            r"ignore\s+(previous|prior|above|all)\s+(instructions?|prompts?|context|rules?)",
            re.IGNORECASE,
        ),
    ),
    (
        "instruction-override",
        re.compile(
            r"disregard\s+(previous|prior|above|all)\s+(instructions?|prompts?|context|rules?)",
            re.IGNORECASE,
        ),
    ),
    (
        "system-prompt-leak",
        re.compile(
            r"(print|output|repeat|reveal|show)\s+(your\s+)?(system\s+prompt|instructions?|context)",
            re.IGNORECASE,
        ),
    ),
    # Hidden Unicode steering characters. Patterns are built via chr() so the
    # source file stays free of the actual control chars (PLE2502/PLE2515).
    (
        "hidden-unicode-rtlo",
        re.compile(chr(0x202E)),  # RIGHT-TO-LEFT OVERRIDE
    ),
    (
        "hidden-unicode-zwj",
        # Zero-width space/non-joiner/joiner/word-joiner/BOM
        re.compile("[" + chr(0x200B) + chr(0x200C) + chr(0x200D) + chr(0x2060) + chr(0xFEFF) + "]"),
    ),
    # HTML/XML comment injection (may hide instructions from display)
    (
        "html-comment-injection",
        re.compile(r"<!--.*?-->", re.DOTALL),
    ),
    # Exfiltration keyword cluster (two or more proximity matches)
    (
        "exfiltration-keywords",
        re.compile(
            r"(send|upload|exfiltrate|transmit|POST|leak).{0,60}(secret|token|key|credential|password|env)",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    # DAN / jailbreak openers
    (
        "jailbreak-opener",
        re.compile(
            r"\b(DAN|jailbreak|developer\s+mode|unrestricted\s+mode)\b",
            re.IGNORECASE,
        ),
    ),
]


def detect_injection(text: str) -> str | None:
    """Return the label of the first matched injection pattern, or ``None``."""
    for label, pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            return label
    return None


def walk_for_injection(arguments: dict[str, Any]) -> str | None:
    """Recursively scan string values in *arguments* for injection patterns.

    Returns the first matched label, or ``None`` if clean.
    """
    for value in _iter_strings(arguments):
        label = detect_injection(value)
        if label is not None:
            return label
    return None


def _iter_strings(obj: Any):  # type: ignore[return]
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _iter_strings(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_strings(item)
