"""Citation-marker utilities shared by RACE and FACT.

Two responsibilities:

* :func:`strip_markers` removes inline citation markers (``[1]``,
  ``[1, 2]``, ``[Smith 2023]``) from a report so the RACE judge scores
  prose, not bibliographic noise.
* :data:`URL_RE` exposes a compiled URL regex used by FACT claim
  extraction.

Both are citation-agnostic: they do not assume any specific citation
style (numeric, author-year, footnote) or provider.
"""

from __future__ import annotations

import re

__all__ = [
    "URL_RE",
    "strip_markers",
]

_BRACKET_MARKER_RE = re.compile(
    r"""
    \[                          # opening bracket
    (?:                         # either…
        \s*\d+(?:\s*[-,]\s*\d+)* # numeric: 1 | 1,2 | 1-3 | 1, 2, 3
      | [^\[\]\n]{1,80}?         # or short, non-nested text (e.g. Author 2023)
    )
    \]
    """,
    re.VERBOSE,
)

URL_RE = re.compile(
    r"https?://[^\s<>\"'\)\]]+",
    re.IGNORECASE,
)


def strip_markers(text: str) -> str:
    """Remove inline citation markers, preserving surrounding text.

    Examples::

        >>> strip_markers("The sky is blue [1].")
        'The sky is blue .'
        >>> strip_markers("Multiple sources [1, 2, 3] agree.")
        'Multiple sources  agree.'
        >>> strip_markers("See [Smith 2023] and [Jones 2024].")
        'See  and .'

    Args:
        text: Raw report text possibly containing citation markers.

    Returns:
        Text with markers removed; whitespace is left intact so that
        downstream tokenization / length heuristics remain stable.
    """
    return _BRACKET_MARKER_RE.sub("", text)
