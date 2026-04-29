r"""Message sanitization — strip problematic byte sequences before LLM API calls.

Surrogate code points, null bytes, and most C0/C1 control characters cause
silent failures or garbled output on some providers (local models, Chromebook
browser transports, byte-level tokenizers). Stripping them here keeps the
harness defensive without burdening individual tool authors.

Allowed control chars: HT (\t), LF (\n), CR (\r) — standard whitespace.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["sanitize_messages", "sanitize_str"]

# Surrogates (U+D800-U+DFFF) - invalid in UTF-8 streams.
# C0 controls except HT/LF/CR, plus DEL (U+007F) and C1 block (U+0080-U+009F).
_STRIP = re.compile(
    r"[\ud800-\udfff"  # surrogates
    r"\x00-\x08\x0b\x0c\x0e-\x1f"  # C0 except HT(\x09) LF(\x0a) CR(\x0d)
    r"\x7f"  # DEL
    r"\x80-\x9f]",  # C1 block
    re.UNICODE,
)


def sanitize_str(s: str) -> str:
    """Remove surrogates, null bytes, and non-whitespace control chars."""
    return _STRIP.sub("", s)


def _sanitize_value(v: Any) -> Any:
    if isinstance(v, str):
        return sanitize_str(v)
    if isinstance(v, list):
        return [_sanitize_value(item) for item in v]
    if isinstance(v, dict):
        return {k: _sanitize_value(val) for k, val in v.items()}
    return v


def sanitize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a new message list with all string values sanitized.

    Does not mutate the input list or its dicts.
    """
    return [_sanitize_value(msg) for msg in messages]
