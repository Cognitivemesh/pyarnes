"""Token-count estimation for prompt-size budgeting.

A char-count / 4 approximation is good enough for English + code; we use
it everywhere we need a fast estimate without paying for a tokenizer.

Centralised here because three call-sites had grown three different
formulas: harness compaction used `len(content) * tokens_per_char`,
burn/optimize used `len(result) // 4`, and the audit subpackage needs
`len(json.dumps(obj)) // 4`. One helper keeps them aligned.
"""

from __future__ import annotations

import json
from typing import Any

__all__ = ["estimate_tokens"]


def estimate_tokens(obj: Any) -> int:
    """Estimate token count from any JSON-serializable object.

    Args:
        obj: A value to size. Strings, dicts, lists, dataclasses-as-dict —
            anything ``json.dumps`` can render. Non-JSON-safe values
            (datetimes, paths, etc.) are coerced via ``default=str``.

    Returns:
        An approximate token count: ``len(json.dumps(obj)) // 4``.
    """
    return len(json.dumps(obj, default=str)) // 4
